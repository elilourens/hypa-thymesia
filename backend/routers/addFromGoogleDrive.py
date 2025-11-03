import logging
from pydantic import BaseModel
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Body
import requests
import re

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


def download_google_drive_file(file_id: str, url: str) -> bytes:
    """
    Download a file from Google Drive, handling confirmation pages and large files.
    """
    logger.info(f"Starting Google Drive download for file: {file_id}")
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    
    try:
        # Use the direct download URL with confirm parameter
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t"
        logger.info(f"Requesting: {download_url}")
        
        response = session.get(download_url, timeout=60, stream=True, allow_redirects=True)
        response.raise_for_status()
        
        content_type = response.headers.get('content-type', '').lower()
        logger.info(f"Response content-type: {content_type}")
        
        # Check if we got HTML instead of the file
        if 'text/html' in content_type:
            logger.warning("Got HTML response, trying alternate method...")
            
            # Try without confirm parameter first
            download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
            response = session.get(download_url, timeout=60, stream=True, allow_redirects=True)
            response.raise_for_status()
            
            content_type = response.headers.get('content-type', '').lower()
            logger.info(f"Retry response content-type: {content_type}")
            
            # If still HTML, try to extract and use confirmation token
            if 'text/html' in content_type:
                logger.info("Still got HTML, extracting confirmation token...")
                html_text = response.text
                
                # Look for the confirmation ID in the HTML
                patterns = [
                    r'"id"\s*:\s*"([a-zA-Z0-9_-]+)"',
                    r'id=["\']([a-zA-Z0-9_-]+)["\']',
                    r'confirm["\']?\s*:\s*["\']([a-zA-Z0-9_-]+)["\']',
                ]
                
                token = None
                for pattern in patterns:
                    match = re.search(pattern, html_text)
                    if match:
                        token = match.group(1)
                        logger.info(f"Found token: {token[:20]}...")
                        break
                
                if token:
                    download_url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm={token}"
                    logger.info(f"Retrying with confirmation token...")
                    response = session.get(download_url, timeout=60, stream=True, allow_redirects=True)
                    response.raise_for_status()
                    content_type = response.headers.get('content-type', '').lower()
                    logger.info(f"Token retry response content-type: {content_type}")
                    
                    # CRITICAL FIX: Verify we got actual file, not HTML
                    if 'text/html' in content_type:
                        logger.error("Still receiving HTML after token retry - file download failed")
                        raise Exception("Failed to download file from Google Drive - still receiving HTML response after confirmation token")
                else:
                    logger.error("Could not extract confirmation token from HTML")
                    raise Exception("Unable to extract Google Drive confirmation token")
        
        # Download the file content
        content = b''
        chunk_size = 8192
        chunk_count = 0
        
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                content += chunk
                chunk_count += 1
                if chunk_count % 100 == 0:
                    logger.info(f"Downloaded {len(content)} bytes...")
        
        logger.info(f"Download complete: {len(content)} bytes total")
        
        # Validate we got actual file content
        if len(content) < 100:
            logger.error(f"Downloaded content too small: {len(content)} bytes")
            raise Exception(f"File too small ({len(content)} bytes) - may be invalid")
        
        # Check if content is still HTML (common with large files)
        if content.startswith(b'<!DOCTYPE') or content.startswith(b'<html') or content.startswith(b'<HTML'):
            logger.error("Downloaded content is HTML, not the actual file")
            logger.debug(f"Content preview: {content[:500]}")
            raise Exception("Google Drive returned HTML instead of file. Try sharing the file directly instead of just viewing access.")
        
        logger.info(f"✓ Successfully downloaded valid file: {len(content)} bytes")
        return content
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error during download: {e}")
        raise Exception(f"Network error: {str(e)}")
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise
    finally:
        session.close()


@router.post("/ingest-google-drive-file")
async def ingest_google_drive_file(
    auth: AuthUser = Depends(get_current_user),
    supabase = Depends(get_supabase),
    settings = Depends(get_settings),
    request: IngestGoogleDriveFileRequest = Body(...)
):
    """
    Ingest a Google Drive file by downloading it and storing a reference.
    For images: Store reference + embed to Pinecone
    For documents: Extract text, store reference, embed text to Pinecone
    """
    user_id = auth.id
    logger.info(f"Ingesting Google Drive file: {request.filename} (ID: {request.google_drive_id})")

    # --- Download file from Google Drive ---
    try:
        logger.info(f"Starting download from Google Drive: {request.google_drive_url}")
        content = download_google_drive_file(request.google_drive_id, request.google_drive_url)
        logger.info(f"Successfully downloaded {len(content)} bytes from Google Drive")
    except Exception as e:
        logger.error(f"Failed to download from Google Drive: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to download file from Google Drive: {str(e)}")

    # --- Use virtual reference path ---
    storage_path = f"google-drive/{request.google_drive_id}/{request.filename}"
    
    # --- Storage metadata for Google Drive reference ---
    storage_metadata = {
        "storage_provider": "google_drive",
        "external_id": request.google_drive_id,
        "external_url": request.google_drive_url,
        "bucket": "google-drive",
    }
    
    try:
        result = await ingest_file_content(
            file_content=content,
            filename=request.filename,
            mime_type=request.mime_type,
            user_id=user_id,
            supabase=supabase,
            settings=settings,
            storage_path=storage_path,
            extract_deep_embeds=request.extract_deep_embeds,
            group_id=request.group_id,
            storage_metadata=storage_metadata,
        )
        logger.info(f"Google Drive file ingestion complete: {result}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Error during ingestion: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")