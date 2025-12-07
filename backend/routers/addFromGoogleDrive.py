import logging
from pydantic import BaseModel
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Body
import requests
import os
from datetime import datetime, timedelta, timezone

from core.config import get_settings
from core.deps import get_supabase
from core.security import get_current_user, AuthUser
from ingestion.ingest_common import ingest_file_content

logger = logging.getLogger(__name__)
router = APIRouter(tags=["google_drive"])


class IngestGoogleDriveFileRequest(BaseModel):
    google_drive_id: str
    google_drive_url: str
    filename: str
    mime_type: str
    size_bytes: int
    group_id: Optional[str] = None
    extract_deep_embeds: bool = True


def _get_stored_token(user_id: str, supabase, provider: str = "google"):
    """Retrieve the most recent stored token for a user"""
    try:
        response = supabase.table("user_oauth_tokens").select("*").eq(
            "user_id", user_id
        ).eq(
            "provider", provider
        ).order(
            "created_at", desc=True
        ).limit(1).execute()

        return response.data[0] if response.data else None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


def _refresh_access_token(refresh_token: str, supabase, user_id: str):
    """
    Refresh an expired access token using the refresh token.
    Updates the database with the new token.
    """
    try:
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

        if not client_id or not client_secret:
            raise HTTPException(status_code=500, detail="Google credentials not configured")

        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }

        response = requests.post(token_url, data=payload, timeout=10)

        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to refresh Google token")

        token_data = response.json()
        new_access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in", 3600)
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

        # Update token in database
        supabase.table("user_oauth_tokens").update({
            "access_token": new_access_token,
            "expires_at": expires_at
        }).eq("user_id", user_id).eq("provider", "google").execute()

        return new_access_token
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail="Failed to refresh token with Google")


def _get_valid_access_token(user_id: str, supabase) -> str:
    """
    Get a valid Google access token, refreshing if necessary.
    Returns the access token ready to use with Google APIs.
    """
    token_record = _get_stored_token(user_id, supabase)

    if not token_record or not token_record.get("access_token"):
        raise HTTPException(status_code=404, detail="No Google account linked")

    access_token = token_record.get("access_token")
    expires_at = token_record.get("expires_at")
    refresh_token = token_record.get("refresh_token")

    # Check if token is expired or expiring soon (within 5 minutes)
    if expires_at:
        try:
            if isinstance(expires_at, str):
                expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            else:
                expires_dt = expires_at

            now = datetime.now(timezone.utc)

            if now >= expires_dt - timedelta(minutes=5):
                if not refresh_token:
                    raise HTTPException(
                        status_code=401,
                        detail="Token expired and no refresh token available"
                    )
                access_token = _refresh_access_token(refresh_token, supabase, user_id)
        except Exception:
            if refresh_token:
                access_token = _refresh_access_token(refresh_token, supabase, user_id)
            else:
                raise HTTPException(
                    status_code=401,
                    detail="Token expired and no refresh token available"
                )

    return access_token


def download_google_drive_file(file_id: str, access_token: str, mime_type: str = None) -> bytes:
    """
    Download a file from Google Drive using authenticated Google Drive API.
    Uses the access token to download files from user's private Drive.
    For Google Docs, Sheets, and Slides, exports as PDF.
    """
    try:
        # Map Google Workspace MIME types to export formats
        google_export_formats = {
            'application/vnd.google-apps.document': 'application/pdf',
            'application/vnd.google-apps.spreadsheet': 'application/pdf',
            'application/vnd.google-apps.presentation': 'application/pdf'
        }

        # Check if this is a Google Workspace file that needs export
        if mime_type and mime_type in google_export_formats:
            export_mime = google_export_formats[mime_type]
            download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}/export?mimeType={export_mime}"
        else:
            # Use Google Drive API v3 to download file content
            download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"

        headers = {
            'Authorization': f'Bearer {access_token}',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(download_url, headers=headers, timeout=60, stream=True)

        # Handle common errors
        if response.status_code == 401:
            logger.error("Unauthorized - token may be invalid or expired")
            raise HTTPException(status_code=401, detail="Google token invalid. Please relink your account.")

        if response.status_code == 403:
            logger.error("Forbidden - insufficient permissions")
            raise HTTPException(status_code=403, detail="Insufficient permissions to access this file")

        if response.status_code == 404:
            logger.error("File not found")
            raise HTTPException(status_code=404, detail="File not found in Google Drive")

        response.raise_for_status()

        # Download the file content
        content = b''
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                content += chunk

        # Validate we got actual file content
        if len(content) == 0:
            raise Exception("Downloaded file is empty")

        # For PDFs, validate the file header
        if mime_type and mime_type in google_export_formats.values():
            if not content.startswith(b'%PDF'):
                logger.error(f"Invalid PDF format. First 20 bytes: {content[:20]}")
                raise Exception("Downloaded file is not a valid PDF")

        return content

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error during download: {e}")
        raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@router.post("/ingest-google-drive-file")
async def ingest_google_drive_file(
    auth: AuthUser = Depends(get_current_user),
    supabase = Depends(get_supabase),
    settings = Depends(get_settings),
    request: IngestGoogleDriveFileRequest = Body(...)
):
    """
    Ingest a Google Drive file by downloading it and uploading to Supabase storage.
    For images: Upload to Supabase + embed to Pinecone
    For documents: Upload to Supabase, extract text, embed to Pinecone
    """
    user_id = auth.id
    logger.info(f"Importing from Google Drive: {request.filename}")

    # --- Get valid access token ---
    try:
        access_token = _get_valid_access_token(user_id, supabase)
    except HTTPException as e:
        logger.error(f"Failed to get access token: {e.detail}")
        raise

    # --- Download file from Google Drive ---
    try:
        content = download_google_drive_file(request.google_drive_id, access_token, request.mime_type)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to download file from Google Drive: {str(e)}")

    # --- Upload to Supabase storage ---
    from uuid import uuid4
    import re

    # Sanitize filename - remove/replace invalid characters
    def sanitize_filename(filename: str) -> str:
        """Remove or replace characters that are invalid in storage paths"""
        # Replace problematic characters with underscores
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # Remove any control characters
        filename = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', filename)
        # Collapse multiple underscores/spaces
        filename = re.sub(r'[_\s]+', '_', filename)
        # Trim underscores from start/end
        filename = filename.strip('_')
        return filename

    # Handle Google Workspace files - they're exported as PDF
    google_workspace_types = {
        'application/vnd.google-apps.document': '.pdf',
        'application/vnd.google-apps.spreadsheet': '.pdf',
        'application/vnd.google-apps.presentation': '.pdf'
    }

    if request.mime_type in google_workspace_types:
        # Google Workspace files are exported as PDF, update filename and mime_type
        base_filename = request.filename.rsplit(".", 1)[0] if "." in request.filename else request.filename
        base_filename = sanitize_filename(base_filename)
        filename = f"{base_filename}.pdf"
        mime_type = "application/pdf"
        ext = "pdf"
    else:
        filename = sanitize_filename(request.filename)
        mime_type = request.mime_type
        ext = request.filename.rsplit(".", 1)[-1].lower() if "." in request.filename else ""

    # Determine bucket based on file type
    bucket = "images" if ext in ("png", "jpeg", "jpg", "webp") else "texts"
    storage_path = f"uploads/{uuid4()}_{filename}"

    try:
        # Upload with explicit content type
        supabase.storage.from_(bucket).upload(
            storage_path,
            content,
            {"content-type": mime_type or "application/octet-stream"}
        )
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload file to Supabase: {str(e)}")

    # --- Ingest using standard flow ---
    try:
        result = await ingest_file_content(
            file_content=content,
            filename=filename,
            mime_type=mime_type,
            user_id=user_id,
            supabase=supabase,
            settings=settings,
            storage_path=storage_path,
            extract_deep_embeds=request.extract_deep_embeds,
            group_id=request.group_id,
            storage_metadata=None,
        )
        logger.info(f"Import complete: {result.get('text_chunks_ingested', 0)} chunks, {result.get('images_extracted', 0)} images")
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")