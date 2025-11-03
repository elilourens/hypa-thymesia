import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from core.security import get_current_user, AuthUser
from core.deps import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/storage", tags=["storage"])

@router.get("/signed-url")
def get_signed_url(
    bucket: str = Query(...),
    path: str = Query(...),
    auth: AuthUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    """
    Lazily generate a signed URL for any object in Supabase storage or Google Drive.
    
    Handles:
    - Supabase files: bucket="images", path="..."
    - Google Drive files: bucket="google-drive", path="google-drive/{FILE_ID}/{FILENAME}"
    
    For Google Drive files, returns:
    - Thumbnail URL for image previews (works in <img> tags)
    - Preview URL for opening in browser
    - Download URL for direct download
    """
    logger.info(f"Getting signed URL for: bucket={bucket}, path={path}")
    
    try:
        # Handle Google Drive files
        if bucket == "google-drive" or path.startswith("google-drive/"):
            logger.info(f"Detected Google Drive file, extracting file ID from path: {path}")
            
            # Extract Google Drive file ID from path
            # Path format: google-drive/{FILE_ID}/{FILENAME}
            # We need to extract just the FILE_ID (first part after google-drive/)
            parts = path.replace("google-drive/", "").split("/")
            file_id = parts[0] if parts else None
            
            if not file_id:
                logger.error(f"Could not extract file ID from path: {path}")
                raise ValueError("No file ID in Google Drive path")
            
            logger.info(f"Extracted Google Drive file ID: {file_id}")
            
            # Return Google Drive thumbnail URL for image previews
            # This works directly in <img> tags without authentication
            thumbnail_url = f"https://drive.google.com/thumbnail?id={file_id}&sz=w400"
            logger.info(f"Returning Google Drive thumbnail URL: {thumbnail_url}")
            return {
                "signed_url": thumbnail_url,
                "provider": "google_drive",
                "file_id": file_id
            }
        
        # Handle regular Supabase files
        logger.info(f"Generating Supabase signed URL for bucket: {bucket}, path: {path}")
        
        res = supabase.storage.from_(bucket).create_signed_url(path, expires_in=3600)
        signed_url = res.get("signedURL")
        if not signed_url:
            logger.error(f"Supabase did not return a signed URL for: {path}")
            raise HTTPException(500, detail="Supabase did not return a signed URL.")
        
        logger.info(f"Generated signed URL successfully for: {path}")
        return {
            "signed_url": signed_url,
            "provider": "supabase"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create signed URL: {e}", exc_info=True)
        raise HTTPException(500, detail=f"Failed to create signed URL: {str(e)}")