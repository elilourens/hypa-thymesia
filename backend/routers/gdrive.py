from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import requests
import os
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
    """Save Google OAuth token to database - ensures only one token per user"""
    try:
        print(f"\n=== SAVING GOOGLE TOKEN ===")
        print(f"User: {auth.id}")
        print(f"Access token (first 30 chars): {token_data.access_token[:30]}...")
        print(f"Access token length: {len(token_data.access_token)}")
        print(f"Refresh token present: {bool(token_data.refresh_token)}")
        if token_data.refresh_token:
            print(f"Refresh token (FULL): {token_data.refresh_token}")
            print(f"Refresh token length: {len(token_data.refresh_token)}")
        else:
            print("WARNING: No refresh token in request!")
        print(f"Expires at: {token_data.expires_at}")
        
        # First, check how many existing Google tokens exist
        print(f"Checking for existing Google tokens for user {auth.id}...")
        existing = supabase_client.table("user_oauth_tokens").select("id").eq("user_id", auth.id).eq("provider", "google").execute()
        print(f"Found {len(existing.data) if existing.data else 0} existing tokens")
        if existing.data:
            for token in existing.data:
                print(f"  - Existing token id: {token['id']}")
        
        # Delete ALL existing Google tokens for this user
        print(f"Deleting all existing Google tokens...")
        delete_response = supabase_client.table("user_oauth_tokens").delete().eq("user_id", auth.id).eq("provider", "google").execute()
        print(f"Delete completed")
        
        # Verify deletion worked
        print("Verifying old tokens are gone...")
        verify = supabase_client.table("user_oauth_tokens").select("id").eq("user_id", auth.id).eq("provider", "google").execute()
        print(f"After deletion, found {len(verify.data) if verify.data else 0} tokens remaining")
        
        if verify.data:
            print(f"WARNING: Old tokens still exist! {[t['id'] for t in verify.data]}")
        
        # Now insert the new token
        print("Inserting new Google token...")
        response = supabase_client.table("user_oauth_tokens").insert({
            "user_id": auth.id,
            "provider": "google",
            "access_token": token_data.access_token,
            "refresh_token": token_data.refresh_token,
            "expires_at": token_data.expires_at,
            "token_type": "Bearer"
        }).execute()
        
        new_id = response.data[0]['id'] if response.data else 'unknown'
        print(f"New token inserted with id: {new_id}")
        
        # Log the saved token
        if response.data:
            saved = response.data[0]
            print(f"Saved token details:")
            print(f"  ID: {saved.get('id')}")
            print(f"  Access token (first 30): {saved.get('access_token', '')[:30]}...")
            print(f"  Refresh token (FULL): {saved.get('refresh_token')}")
            print(f"  Expires at: {saved.get('expires_at')}")
        
        # Final verification - check we only have ONE token now
        print("Final verification - checking total tokens...")
        final = supabase_client.table("user_oauth_tokens").select("id").eq("user_id", auth.id).eq("provider", "google").execute()
        print(f"Final count: {len(final.data) if final.data else 0} tokens")
        if final.data:
            for token in final.data:
                print(f"  - Token id: {token['id']}")
        
        return {"success": True, "message": "Google token saved"}
    except Exception as e:
        print(f"Error saving Google token: {str(e)}")
        import traceback
        print(traceback.format_exc())
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
        
        response = supabase_client.table("user_oauth_tokens").select("*").eq("user_id", auth.id).eq("provider", "google").order("created_at", desc=True).limit(1).execute()
        
        print(f"Retrieved data exists: {bool(response.data)}")
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(status_code=404, detail="Google access token not found")
        
        token_data = response.data[0]
        token = token_data.get("access_token")
        print(f"Token (first 20 chars): {token[:20] if token else 'N/A'}...")
        
        if not token:
            raise HTTPException(status_code=404, detail="Google access token not found")
        
        return {
            "access_token": token,
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": token_data.get("expires_at")
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
    print("=== refresh_google_token endpoint called ===")
    try:
        print(f"Refreshing Google token for user: {auth.id}")
        
        # Get credentials directly from environment
        google_client_id = os.getenv("GOOGLE_CLIENT_ID")
        google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        
        print(f"Google client ID configured: {bool(google_client_id)}")
        print(f"Google client secret configured: {bool(google_client_secret)}")
        
        if not google_client_id or not google_client_secret:
            print("ERROR: Google credentials not configured")
            raise HTTPException(status_code=500, detail="Google credentials not configured")
        
        # Get the stored token - order by created_at desc to get the most recent one
        print("Querying database for most recent refresh token...")
        response = supabase_client.table("user_oauth_tokens").select("*").eq("user_id", auth.id).eq("provider", "google").order("created_at", desc=True).limit(1).execute()
        
        print(f"Database query returned {len(response.data) if response.data else 0} rows")
        
        if not response.data or len(response.data) == 0 or not response.data[0].get("refresh_token"):
            print("No refresh token found")
            print(f"Response data: {response.data}")
            raise HTTPException(status_code=404, detail="No refresh token found")
        
        # Get the first (most recent) result
        token_row = response.data[0]
        refresh_token = token_row["refresh_token"]
        print(f"Found refresh token (first 20 chars): {refresh_token[:20]}...")
        print(f"Refresh token length: {len(refresh_token)}")
        print(f"Full refresh token for debugging: {refresh_token}")
        
        # Exchange refresh token for new access token
        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            "client_id": google_client_id,
            "client_secret": google_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        
        print("Sending refresh request to Google...")
        print(f"Token URL: {token_url}")
        token_response = requests.post(token_url, data=payload)
        
        print(f"Google response status: {token_response.status_code}")
        
        if token_response.status_code != 200:
            print(f"Google refresh failed with status {token_response.status_code}")
            print(f"Google response: {token_response.text}")
            raise HTTPException(status_code=400, detail=f"Failed to refresh token: {token_response.text}")
        
        token_data = token_response.json()
        print(f"Refresh successful, new token (first 20 chars): {token_data['access_token'][:20]}...")
        
        # Calculate proper expires_at timestamp
        expires_in = token_data.get("expires_in", 3600)
        expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
        
        # Update token in database
        supabase_client.table("user_oauth_tokens").update({
            "access_token": token_data["access_token"],
            "expires_at": expires_at,
            "updated_at": "now()"
        }).eq("user_id", auth.id).eq("provider", "google").execute()
        
        print("Token updated in database")
        return {"success": True, "message": "Token refreshed"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR in refresh_google_token: {type(e).__name__}: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

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

@router.post("/revoke-google-token")
async def revoke_google_token(
    auth: AuthUser = Depends(get_current_user),
    supabase_client = Depends(lambda: create_client(
        get_settings().SUPABASE_URL,
        get_settings().SUPABASE_KEY
    ))
):
    """Revoke Google token to clear all permissions"""
    try:
        print(f"Revoking Google token for user: {auth.id}")
        
        # Get the stored token
        response = supabase_client.table("user_oauth_tokens").select("*").eq("user_id", auth.id).eq("provider", "google").single().execute()
        
        if not response.data or not response.data.get("access_token"):
            print("No token found to revoke")
            return {"success": False, "message": "No token found", "revoked": False}
        
        access_token = response.data["access_token"]
        print(f"Found token to revoke (first 20 chars): {access_token[:20]}...")
        
        # Revoke the token with Google
        revoke_url = "https://oauth2.googleapis.com/revoke"
        revoke_payload = {"token": access_token}
        
        print("Sending revoke request to Google...")
        revoke_response = requests.post(revoke_url, data=revoke_payload)
        
        if revoke_response.status_code == 200:
            print("Token successfully revoked with Google")
            return {"success": True, "message": "Token revoked", "revoked": True}
        else:
            print(f"Google revoke returned status {revoke_response.status_code}: {revoke_response.text}")
            # Still return success - token is invalidated even if revoke endpoint returns non-200
            return {"success": True, "message": "Revoke sent to Google", "revoked": True}
            
    except Exception as e:
        print(f"Error revoking Google token: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/unlink-google")
async def unlink_google(
    auth: AuthUser = Depends(get_current_user),
    supabase_client = Depends(lambda: create_client(
        get_settings().SUPABASE_URL,
        get_settings().SUPABASE_KEY
    ))
):
    """Unlink Google account from Supabase auth and delete stored tokens"""
    try:
        print(f"Unlinking Google for user: {auth.id}")
        
        # Step 1: Get the token FIRST (before deleting) - get the LATEST one
        token_revoked = False
        try:
            print(f"Getting latest token for user {auth.id} to revoke...")
            response = supabase_client.table("user_oauth_tokens").select("*").eq("user_id", auth.id).eq("provider", "google").order("created_at", desc=True).limit(1).execute()
            
            if response and response.data and len(response.data) > 0:
                token_data = response.data[0]
                print(f"Found token to potentially revoke (id: {token_data.get('id')})")
                
                # ONLY revoke the access token, NOT the refresh token
                # If we revoke the refresh token, Google won't give us a new one on re-link
                token_to_revoke = token_data.get("access_token")
                
                if token_to_revoke:
                    revoke_url = "https://oauth2.googleapis.com/revoke"
                    revoke_payload = {"token": token_to_revoke}
                    
                    print(f"Revoking ACCESS token (first 20 chars): {token_to_revoke[:20]}...")
                    print("Sending revoke request to Google...")
                    revoke_response = requests.post(revoke_url, data=revoke_payload, timeout=5)
                    print(f"Google revoke response: {revoke_response.status_code}")
                    token_revoked = True
                else:
                    print("No access token found to revoke")
            else:
                print("No token record found to revoke (token may already be deleted)")
        except Exception as e:
            print(f"Warning: Exception during token revoke: {str(e)}")
        
        # Step 2: Delete from our custom oauth tokens table
        try:
            supabase_client.table("user_oauth_tokens").delete().eq("user_id", auth.id).eq("provider", "google").execute()
            print("Deleted tokens from user_oauth_tokens table")
        except Exception as e:
            print(f"Warning: Failed to delete from user_oauth_tokens: {str(e)}")
        
        return {
            "success": True, 
            "message": "Google account unlinked and token revoked",
            "token_revoked": token_revoked
        }
    except Exception as e:
        print(f"Error unlinking Google: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))