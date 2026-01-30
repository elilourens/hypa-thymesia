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
from core.token_encryption import encrypt_token, decrypt_token, is_token_encrypted

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
    """
    Retrieve the most recent stored token for a user.
    Automatically decrypts tokens if they are encrypted.
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        response = supabase_client.table("user_oauth_tokens").select("*").eq(
            "user_id", user_id
        ).eq(
            "provider", provider
        ).order(
            "created_at", desc=True
        ).limit(1).execute()

        if not response.data:
            return None

        token_record = response.data[0]

        # Decrypt tokens if they exist and are encrypted
        if token_record.get("access_token"):
            try:
                # Check if token is encrypted (for backwards compatibility during migration)
                if is_token_encrypted(token_record["access_token"]):
                    token_record["access_token"] = decrypt_token(token_record["access_token"])
            except Exception as e:
                logger.warning(f"Failed to decrypt access_token: {e}")
                # Token might be plaintext during migration - continue

        if token_record.get("refresh_token"):
            try:
                if is_token_encrypted(token_record["refresh_token"]):
                    token_record["refresh_token"] = decrypt_token(token_record["refresh_token"])
            except Exception as e:
                logger.warning(f"Failed to decrypt refresh_token: {e}")
                # Token might be plaintext during migration - continue

        return token_record
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
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

        # Encrypt token before storing in database
        encrypted_access_token = encrypt_token(new_access_token)

        # Update token in database
        supabase_client.table("user_oauth_tokens").update({
            "access_token": encrypted_access_token,
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

    # Log token state for debugging
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Token check: has_refresh_token={bool(refresh_token)}, expires_at={expires_at}")

    # Check if token is expired or expiring soon (within 5 minutes)
    if expires_at:
        try:
            # Parse expires_at, handling both naive and timezone-aware datetimes
            if isinstance(expires_at, str):
                expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            else:
                expires_dt = expires_at

            # Use timezone-aware datetime
            now = datetime.now(timezone.utc)
            logger.info(f"Token expiry check: now={now}, expires={expires_dt}, is_expired={now >= expires_dt - timedelta(minutes=5)}")

            if now >= expires_dt - timedelta(minutes=5):
                if not refresh_token:
                    logger.error("Token expired but no refresh token available")
                    raise HTTPException(
                        status_code=401,
                        detail="Token expired and no refresh token available. Please relink your Google account."
                    )

                # Refresh the token
                logger.info("Refreshing access token...")
                access_token = _refresh_access_token(
                    refresh_token,
                    supabase_client,
                    user_id,
                    google_credentials
                )
                logger.info("Token refreshed successfully")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Error checking token expiry: {e}")
            # If datetime parsing fails, assume token is expired
            if refresh_token:
                logger.info("Attempting to refresh token due to parsing error...")
                access_token = _refresh_access_token(
                    refresh_token,
                    supabase_client,
                    user_id,
                    google_credentials
                )
            else:
                logger.error("Token may be expired and no refresh token available")
                raise HTTPException(
                    status_code=401,
                    detail="Token expired and no refresh token available. Please relink your Google account."
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

        # Encrypt tokens before storing
        encrypted_access_token = encrypt_token(token_data.access_token)
        encrypted_refresh_token = encrypt_token(token_data.refresh_token) if token_data.refresh_token else None

        # Insert new token
        result = supabase_client.table("user_oauth_tokens").insert({
            "user_id": auth.id,
            "provider": "google",
            "access_token": encrypted_access_token,
            "refresh_token": encrypted_refresh_token,
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


@router.get("/google-needs-consent")
async def check_google_needs_consent(
    auth: AuthUser = Depends(get_current_user),
    supabase_client=Depends(get_supabase_client)
):
    """
    Check if user needs to consent to get a refresh token.
    Returns True if user has a token but no refresh token.
    """
    try:
        token_record = _get_stored_token(auth.id, supabase_client)

        if not token_record:
            return {"needs_consent": False}  # No token at all, normal flow

        # Check if we have a refresh token
        has_refresh_token = bool(token_record.get("refresh_token"))

        return {"needs_consent": not has_refresh_token}
    except Exception:
        return {"needs_consent": False}


@router.get("/google-linked")
async def check_google_linked(
    auth: AuthUser = Depends(get_current_user),
    supabase_client=Depends(get_supabase_client),
    google_credentials: dict = Depends(get_google_credentials)
):
    """
    Check if user has a valid Google account linked.
    Attempts to refresh token if expired.
    Returns linked=false only if no token or refresh fails.
    """
    try:
        # Try to get a valid token (will auto-refresh if needed)
        _get_valid_access_token(
            auth.id,
            supabase_client,
            google_credentials
        )
        return {"linked": True}
    except HTTPException as e:
        # If 401 (no refresh token), return not linked
        # If 404 (no token at all), return not linked
        if e.status_code in [401, 404]:
            return {"linked": False}
        # Other errors, assume not linked to be safe
        return {"linked": False}
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