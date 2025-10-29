# app/api/routes/storage.py
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
    - Google Drive files: bucket="google-drive", path="google-drive/{FILE_ID}"
    """
    logger.info(f"Getting signed URL for: bucket={bucket}, path={path}")
    
    try:
        # Handle Google Drive files
        if bucket == "google-drive" or path.startswith("google-drive/"):
            logger.info(f"Detected Google Drive file, extracting file ID from path")
            
            # Extract Google Drive file ID from path
            file_id = path.replace("google-drive/", "")
            if not file_id:
                raise ValueError("No file ID in Google Drive path")
            
            logger.info(f"Generating Google Drive preview URL for: {file_id}")
            
            # Return Google Drive thumbnail preview URL
            preview_url = f"https://drive.google.com/thumbnail?id={file_id}&sz=w400"
            return {"signed_url": preview_url}
        
        # Handle regular Supabase files
        logger.info(f"Generating Supabase signed URL for bucket: {bucket}, path: {path}")
        
        res = supabase.storage.from_(bucket).create_signed_url(path, expires_in=3600)
        signed_url = res.get("signedURL")
        if not signed_url:
            logger.error(f"Supabase did not return a signed URL for: {path}")
            raise HTTPException(500, detail="Supabase did not return a signed URL.")
        
        logger.info(f"Generated signed URL successfully for: {path}")
        return {"signed_url": signed_url}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create signed URL: {e}", exc_info=True)
        raise HTTPException(500, detail=f"Failed to create signed URL: {str(e)}")