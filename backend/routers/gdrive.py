"""
Google Drive OAuth Integration Router
Handles linking, unlinking, and persistent access to Google Drive files
with automatic token refresh and secure token storage.
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, timezone
import requests
import os
from supabase import create_client
from core.security import get_current_user, AuthUser
from core.config import get_settings

router = APIRouter( tags=["google"])

# ============================================================================
# Models
# ============================================================================

class GoogleTokenRequest(BaseModel):
    """Request model for saving Google OAuth tokens"""
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[str] = None


class GoogleDriveFilesResponse(BaseModel):
    """Response model for Google Drive files list"""
    files: list
    nextPageToken: Optional[str] = None


# ============================================================================
# Dependencies
# ============================================================================

def get_supabase_client():
    """Get Supabase client instance"""
    return create_client(
        get_settings().SUPABASE_URL,
        get_settings().SUPABASE_KEY
    )


def get_google_credentials():
    """Get Google OAuth credentials from environment"""
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=500,
            detail="Google credentials not configured"
        )
    
    return {"client_id": client_id, "client_secret": client_secret}


# ============================================================================
# Token Management (Private)
# ============================================================================

def _get_stored_token(
    user_id: str,
    supabase_client,
    provider: str = "google"
):
    """Retrieve the most recent stored token for a user"""
    try:
        response = supabase_client.table("user_oauth_tokens").select("*").eq(
            "user_id", user_id
        ).eq(
            "provider", provider
        ).order(
            "created_at", desc=True
        ).limit(1).execute()
        
        return response.data[0] if response.data else None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


def _refresh_access_token(
    refresh_token: str,
    supabase_client,
    user_id: str,
    google_credentials: dict
):
    """
    Refresh an expired access token using the refresh token.
    Updates the database with the new token.
    """
    try:
        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            "client_id": google_credentials["client_id"],
            "client_secret": google_credentials["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        
        response = requests.post(token_url, data=payload, timeout=10)
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail="Failed to refresh Google token"
            )
        
        token_data = response.json()
        new_access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in", 3600)
        # Use timezone-aware datetime
        expires_at = (datetime.utcnow().replace(tzinfo=timezone.utc) + timedelta(seconds=expires_in)).isoformat()
        
        # Update token in database
        supabase_client.table("user_oauth_tokens").update({
            "access_token": new_access_token,
            "expires_at": expires_at
        }).eq("user_id", user_id).eq("provider", "google").execute()
        
        return new_access_token
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to refresh token with Google"
        )


def _get_valid_access_token(
    user_id: str,
    supabase_client,
    google_credentials: dict
) -> str:
    """
    Get a valid Google access token, refreshing if necessary.
    Returns the access token ready to use with Google APIs.
    """
    token_record = _get_stored_token(user_id, supabase_client)

    if not token_record or not token_record.get("access_token"):
        raise HTTPException(
            status_code=404,
            detail="No Google account linked"
        )

    access_token = token_record.get("access_token")
    expires_at = token_record.get("expires_at")
    refresh_token = token_record.get("refresh_token")

    # Check if token is expired or expiring soon (within 5 minutes)
    if expires_at:
        try:
            # Parse expires_at, handling both naive and timezone-aware datetimes
            if isinstance(expires_at, str):
                expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            else:
                expires_dt = expires_at

            # Make current time timezone-aware if expires_dt is aware
            now = datetime.utcnow()
            if expires_dt.tzinfo is not None:
                from datetime import timezone
                now = now.replace(tzinfo=timezone.utc)

            if now >= expires_dt - timedelta(minutes=5):
                if not refresh_token:
                    raise HTTPException(
                        status_code=401,
                        detail="Token expired and no refresh token available"
                    )

                # Refresh the token
                access_token = _refresh_access_token(
                    refresh_token,
                    supabase_client,
                    user_id,
                    google_credentials
                )
        except Exception as e:
            # If datetime parsing fails, assume token is expired
            if refresh_token:
                access_token = _refresh_access_token(
                    refresh_token,
                    supabase_client,
                    user_id,
                    google_credentials
                )
            else:
                raise HTTPException(
                    status_code=401,
                    detail="Token expired and no refresh token available"
                )

    return access_token


def _find_public_folder_id(access_token: str) -> Optional[str]:
    """
    Find the ID of the 'public' folder in the user's Google Drive.
    Returns the folder ID if found, None otherwise.
    """
    try:
        # Search for a folder named "public" (case-insensitive)
        params = {
            "q": "name='public' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            "fields": "files(id, name)",
            "pageSize": 1
        }

        response = requests.get(
            "https://www.googleapis.com/drive/v3/files",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            files = data.get("files", [])
            if files:
                return files[0]["id"]

        return None
    except Exception:
        return None


# ============================================================================
# Public Routes
# ============================================================================

@router.post("/save-google-token")
async def save_google_token(
    auth: AuthUser = Depends(get_current_user),
    supabase_client=Depends(get_supabase_client),
    token_data: GoogleTokenRequest = Body(...)
):
    """
    Save Google OAuth token to database.
    Replaces any existing token for the user (one token per user).
    """
    try:
        # Delete any existing tokens
        supabase_client.table("user_oauth_tokens").delete().eq(
            "user_id", auth.id
        ).eq(
            "provider", "google"
        ).execute()
        
        # Insert new token
        result = supabase_client.table("user_oauth_tokens").insert({
            "user_id": auth.id,
            "provider": "google",
            "access_token": token_data.access_token,
            "refresh_token": token_data.refresh_token,
            "expires_at": token_data.expires_at,
            "token_type": "Bearer"
        }).execute()
        
        return {
            "success": True,
            "message": "Token saved successfully"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save token: {str(e)}"
        )


@router.get("/google-linked")
async def check_google_linked(
    auth: AuthUser = Depends(get_current_user),
    supabase_client=Depends(get_supabase_client)
):
    """Check if user has a Google account linked"""
    try:
        token_record = _get_stored_token(auth.id, supabase_client)
        
        return {
            "linked": token_record is not None
        }
    except Exception:
        return {"linked": False}


@router.get("/google-drive-files")
async def get_google_drive_files(
    auth: AuthUser = Depends(get_current_user),
    supabase_client=Depends(get_supabase_client),
    google_credentials: dict = Depends(get_google_credentials),
    page_size: int = 100,
    page_token: Optional[str] = None
):
    """
    Fetch files from user's Google Drive 'public' folder only.
    Automatically refreshes token if expired.
    """
    try:
        # Get valid access token (refreshes if needed)
        access_token = _get_valid_access_token(
            auth.id,
            supabase_client,
            google_credentials
        )

        # Find the 'public' folder ID
        public_folder_id = _find_public_folder_id(access_token)

        if not public_folder_id:
            raise HTTPException(
                status_code=404,
                detail="No 'public' folder found in Google Drive. Please create a folder named 'public' in your Google Drive root."
            )

        # Build query parameters to only get files inside the 'public' folder
        params = {
            "pageSize": page_size,
            "spaces": "drive",
            "fields": "files(id,name,mimeType,createdTime,modifiedTime,webViewLink,size),nextPageToken",
            "q": f"'{public_folder_id}' in parents and trashed=false"
        }

        if page_token:
            params["pageToken"] = page_token

        # Call Google Drive API
        response = requests.get(
            "https://www.googleapis.com/drive/v3/files",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )

        if response.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail="Google token invalid. Please relink your account."
            )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Failed to fetch files from Google Drive"
            )

        return response.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching files: {str(e)}"
        )


@router.delete("/unlink-google")
async def unlink_google(
    auth: AuthUser = Depends(get_current_user),
    supabase_client=Depends(get_supabase_client),
    google_credentials: dict = Depends(get_google_credentials)
):
    """
    Unlink Google account from Supabase auth and delete stored tokens.
    Revokes tokens with Google to clear permissions.
    """
    try:
        # Get the token before deleting it
        token_record = _get_stored_token(auth.id, supabase_client)
        token_revoked = False
        
        if token_record:
            access_token = token_record.get("access_token")
            
            # Revoke the access token with Google
            if access_token:
                try:
                    revoke_url = "https://oauth2.googleapis.com/revoke"
                    revoke_payload = {"token": access_token}
                    
                    revoke_response = requests.post(
                        revoke_url,
                        data=revoke_payload,
                        timeout=5
                    )
                    
                    token_revoked = revoke_response.status_code == 200
                except Exception:
                    # Even if revoke fails, continue with local cleanup
                    pass
        
        # Delete tokens from database
        supabase_client.table("user_oauth_tokens").delete().eq(
            "user_id", auth.id
        ).eq(
            "provider", "google"
        ).execute()
        
        return {
            "success": True,
            "message": "Google account unlinked",
            "token_revoked": token_revoked
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to unlink: {str(e)}"
        )