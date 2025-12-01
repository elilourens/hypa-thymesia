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
    Generate a signed URL for any object in Supabase storage.
    """
    logger.info(f"Getting signed URL for: bucket={bucket}, path={path}")

    try:
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