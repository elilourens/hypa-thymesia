"""
OneDrive/SharePoint OAuth Integration Router
Handles linking, unlinking, and persistent access to OneDrive/SharePoint files
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

router = APIRouter(tags=["onedrive"])

# ============================================================================
# Models
# ============================================================================

class MicrosoftTokenRequest(BaseModel):
    """Request model for saving Microsoft OAuth tokens"""
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[str] = None


class OneDriveFilesResponse(BaseModel):
    """Response model for OneDrive files list"""
    files: list
    nextLink: Optional[str] = None


# ============================================================================
# Dependencies
# ============================================================================

def get_supabase_client():
    """Get Supabase client instance"""
    return create_client(
        get_settings().SUPABASE_URL,
        get_settings().SUPABASE_KEY
    )


def get_microsoft_credentials():
    """Get Microsoft OAuth credentials from environment"""
    client_id = os.getenv("MICROSOFT_CLIENT_ID")
    client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
    tenant_id = os.getenv("MICROSOFT_TENANT_ID", "common")

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=500,
            detail="Microsoft credentials not configured"
        )

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "tenant_id": tenant_id
    }


# ============================================================================
# Token Management (Private)
# ============================================================================

def _get_stored_token(
    user_id: str,
    supabase_client,
    provider: str = "microsoft"
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
    microsoft_credentials: dict
):
    """
    Refresh an expired access token using the refresh token.
    Updates the database with the new token.
    """
    try:
        tenant_id = microsoft_credentials.get("tenant_id", "common")
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

        payload = {
            "client_id": microsoft_credentials["client_id"],
            "client_secret": microsoft_credentials["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": "Files.Read.All Sites.Read.All offline_access"
        }

        response = requests.post(token_url, data=payload, timeout=10)

        if response.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail="Failed to refresh Microsoft token"
            )

        token_data = response.json()
        new_access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in", 3600)
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

        # Update token in database
        supabase_client.table("user_oauth_tokens").update({
            "access_token": new_access_token,
            "expires_at": expires_at
        }).eq("user_id", user_id).eq("provider", "microsoft").execute()

        return new_access_token
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to refresh token with Microsoft"
        )


def _get_valid_access_token(
    user_id: str,
    supabase_client,
    microsoft_credentials: dict
) -> str:
    """
    Get a valid Microsoft access token, refreshing if necessary.
    Returns the access token ready to use with Microsoft Graph API.
    """
    token_record = _get_stored_token(user_id, supabase_client)

    if not token_record or not token_record.get("access_token"):
        raise HTTPException(
            status_code=404,
            detail="No Microsoft account linked"
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
            if isinstance(expires_at, str):
                expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            else:
                expires_dt = expires_at

            now = datetime.now(timezone.utc)
            logger.info(f"Token expiry check: now={now}, expires={expires_dt}, is_expired={now >= expires_dt - timedelta(minutes=5)}")

            if now >= expires_dt - timedelta(minutes=5):
                if not refresh_token:
                    logger.error("Token expired but no refresh token available")
                    raise HTTPException(
                        status_code=401,
                        detail="Token expired and no refresh token available. Please relink your Microsoft account."
                    )

                logger.info("Refreshing access token...")
                access_token = _refresh_access_token(
                    refresh_token,
                    supabase_client,
                    user_id,
                    microsoft_credentials
                )
                logger.info("Token refreshed successfully")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Error checking token expiry: {e}")
            if refresh_token:
                logger.info("Attempting to refresh token due to parsing error...")
                access_token = _refresh_access_token(
                    refresh_token,
                    supabase_client,
                    user_id,
                    microsoft_credentials
                )
            else:
                logger.error("Token may be expired and no refresh token available")
                raise HTTPException(
                    status_code=401,
                    detail="Token expired and no refresh token available. Please relink your Microsoft account."
                )

    return access_token


# ============================================================================
# Public Routes
# ============================================================================

@router.post("/save-microsoft-token")
async def save_microsoft_token(
    auth: AuthUser = Depends(get_current_user),
    supabase_client=Depends(get_supabase_client),
    token_data: MicrosoftTokenRequest = Body(...)
):
    """
    Save Microsoft OAuth token to database.
    Replaces any existing token for the user (one token per user).
    """
    try:
        # Delete any existing tokens
        supabase_client.table("user_oauth_tokens").delete().eq(
            "user_id", auth.id
        ).eq(
            "provider", "microsoft"
        ).execute()

        # Insert new token
        result = supabase_client.table("user_oauth_tokens").insert({
            "user_id": auth.id,
            "provider": "microsoft",
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


@router.get("/microsoft-needs-consent")
async def check_microsoft_needs_consent(
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
            return {"needs_consent": False}

        has_refresh_token = bool(token_record.get("refresh_token"))

        return {"needs_consent": not has_refresh_token}
    except Exception:
        return {"needs_consent": False}


@router.get("/microsoft-linked")
async def check_microsoft_linked(
    auth: AuthUser = Depends(get_current_user),
    supabase_client=Depends(get_supabase_client),
    microsoft_credentials: dict = Depends(get_microsoft_credentials)
):
    """
    Check if user has a valid Microsoft account linked.
    Attempts to refresh token if expired.
    """
    try:
        _get_valid_access_token(
            auth.id,
            supabase_client,
            microsoft_credentials
        )
        return {"linked": True}
    except HTTPException as e:
        if e.status_code in [401, 404]:
            return {"linked": False}
        return {"linked": False}
    except Exception:
        return {"linked": False}


@router.get("/onedrive-files")
async def get_onedrive_files(
    auth: AuthUser = Depends(get_current_user),
    supabase_client=Depends(get_supabase_client),
    microsoft_credentials: dict = Depends(get_microsoft_credentials),
    page_size: int = 100,
    next_link: Optional[str] = None
):
    """
    Fetch files from user's OneDrive root folder.
    Automatically refreshes token if expired.
    """
    try:
        access_token = _get_valid_access_token(
            auth.id,
            supabase_client,
            microsoft_credentials
        )

        # Use Microsoft Graph API to list files
        if next_link:
            graph_url = next_link
        else:
            graph_url = f"https://graph.microsoft.com/v1.0/me/drive/root/children?$top={page_size}"

        response = requests.get(
            graph_url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )

        if response.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail="Microsoft token invalid. Please relink your account."
            )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Failed to fetch files from OneDrive"
            )

        data = response.json()

        # Transform Microsoft Graph response to match our interface
        files = []
        for item in data.get("value", []):
            # Skip folders, packages (like Personal Vault), and other non-file items
            # Only include items that have a "file" property
            if "file" not in item:
                continue

            files.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "mimeType": item.get("file", {}).get("mimeType") or "application/octet-stream",
                "createdTime": item.get("createdDateTime"),
                "modifiedTime": item.get("lastModifiedDateTime"),
                "webViewLink": item.get("webUrl"),
                "size": item.get("size")
            })

        return {
            "files": files,
            "nextLink": data.get("@odata.nextLink")
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching files: {str(e)}"
        )


@router.delete("/unlink-microsoft")
async def unlink_microsoft(
    auth: AuthUser = Depends(get_current_user),
    supabase_client=Depends(get_supabase_client),
    microsoft_credentials: dict = Depends(get_microsoft_credentials)
):
    """
    Unlink Microsoft account and delete stored tokens.
    """
    try:
        # Delete tokens from database
        supabase_client.table("user_oauth_tokens").delete().eq(
            "user_id", auth.id
        ).eq(
            "provider", "microsoft"
        ).execute()

        return {
            "success": True,
            "message": "Microsoft account unlinked"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to unlink: {str(e)}"
        )
