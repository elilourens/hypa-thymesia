from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from typing import Optional
import requests
from supabase import create_client
from core.security import get_current_user, AuthUser
from core.config import get_settings

router = APIRouter(tags=["google"])

class GoogleTokenRequest(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[str] = None

@router.post("/save-google-token")
async def save_google_token(
    auth: AuthUser = Depends(get_current_user),
    supabase_client = Depends(lambda: create_client(
        get_settings().SUPABASE_URL,
        get_settings().SUPABASE_KEY
    )),
    token_data: GoogleTokenRequest = Body(...)
):
    """Save Google OAuth token to database"""
    try:
        print(f"Saving Google token for user: {auth.id}")
        print(f"Token (first 20 chars): {token_data.access_token[:20]}...")
        print(f"Refresh token present: {bool(token_data.refresh_token)}")
        
        response = supabase_client.table("user_oauth_tokens").upsert({
            "user_id": auth.id,
            "provider": "google",
            "access_token": token_data.access_token,
            "refresh_token": token_data.refresh_token,
            "expires_at": token_data.expires_at,
            "token_type": "Bearer",
            "updated_at": "now()"
        }).execute()
        
        print(f"Save response: {response.data}")
        return {"success": True, "message": "Google token saved"}
    except Exception as e:
        print(f"Error saving Google token: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/google-drive-token")
async def get_google_drive_token(
    auth: AuthUser = Depends(get_current_user),
    supabase_client = Depends(lambda: create_client(
        get_settings().SUPABASE_URL,
        get_settings().SUPABASE_KEY
    ))
):
    """Retrieve Google OAuth token from database"""
    try:
        print(f"Retrieving Google token for user: {auth.id}")
        
        response = supabase_client.table("user_oauth_tokens").select("*").eq("user_id", auth.id).eq("provider", "google").single().execute()
        
        print(f"Retrieved data exists: {bool(response.data)}")
        
        if not response.data or not response.data.get("access_token"):
            raise HTTPException(status_code=404, detail="Google access token not found")
        
        token = response.data["access_token"]
        print(f"Token (first 20 chars): {token[:20]}...")
        
        return {
            "access_token": token,
            "refresh_token": response.data.get("refresh_token"),
            "expires_at": response.data.get("expires_at")
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error retrieving Google token: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/refresh-google-token")
async def refresh_google_token(
    auth: AuthUser = Depends(get_current_user),
    supabase_client = Depends(lambda: create_client(
        get_settings().SUPABASE_URL,
        get_settings().SUPABASE_KEY
    ))
):
    """Refresh expired Google OAuth token"""
    try:
        print(f"Refreshing Google token for user: {auth.id}")
        
        settings = get_settings()
        
        # Get the stored token
        response = supabase_client.table("user_oauth_tokens").select("*").eq("user_id", auth.id).eq("provider", "google").single().execute()
        
        if not response.data or not response.data.get("refresh_token"):
            print("No refresh token found")
            raise HTTPException(status_code=404, detail="No refresh token found")
        
        refresh_token = response.data["refresh_token"]
        print(f"Found refresh token (first 20 chars): {refresh_token[:20]}...")
        
        # Exchange refresh token for new access token
        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            "client_id": settings.SUPABASE_URL,  # You'll need to add these to settings
            "client_secret": settings.SUPABASE_KEY,  # You'll need to add these to settings
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        
        print("Sending refresh request to Google...")
        token_response = requests.post(token_url, data=payload)
        
        if token_response.status_code != 200:
            print(f"Google refresh failed: {token_response.text}")
            raise HTTPException(status_code=400, detail="Failed to refresh token")
        
        token_data = token_response.json()
        print(f"Refresh successful, new token (first 20 chars): {token_data['access_token'][:20]}...")
        
        # Update token in database
        supabase_client.table("user_oauth_tokens").update({
            "access_token": token_data["access_token"],
            "expires_at": token_data.get("expires_in"),
            "updated_at": "now()"
        }).eq("user_id", auth.id).eq("provider", "google").execute()
        
        print("Token updated in database")
        return {"success": True, "message": "Token refreshed"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error refreshing Google token: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/google-linked")
async def check_google_linked(
    auth: AuthUser = Depends(get_current_user),
    supabase_client = Depends(lambda: create_client(
        get_settings().SUPABASE_URL,
        get_settings().SUPABASE_KEY
    ))
):
    """Check if user has Google linked"""
    try:
        response = supabase_client.table("user_oauth_tokens").select("id").eq("user_id", auth.id).eq("provider", "google").single().execute()
        
        return {"linked": bool(response.data)}
    except Exception:
        return {"linked": False}

@router.delete("/unlink-google")
async def unlink_google(
    auth: AuthUser = Depends(get_current_user),
    supabase_client = Depends(lambda: create_client(
        get_settings().SUPABASE_URL,
        get_settings().SUPABASE_KEY
    ))
):
    """Unlink Google account"""
    try:
        supabase_client.table("user_oauth_tokens").delete().eq("user_id", auth.id).eq("provider", "google").execute()
        
        return {"success": True, "message": "Google account unlinked"}
    except Exception as e:
        print(f"Error unlinking Google: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))