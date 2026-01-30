import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from core.security import get_current_user, AuthUser
from core.deps import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/storage", tags=["storage"])


class VideoFileInfo(BaseModel):
    """Response model for video file info."""
    doc_id: str
    filename: str
    bucket: str
    storage_path: str
    mime_type: Optional[str] = None

@router.get("/signed-url")
def get_signed_url(
    bucket: str = Query(...),
    path: str = Query(...),
    download: bool = Query(False, description="If true, forces download; if false, displays inline"),
    auth: AuthUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    """
    Generate a signed URL for any object in Supabase storage.
    """
    logger.info(f"Getting signed URL for: bucket={bucket}, path={path}, download={download}")

    try:
        logger.info(f"Generating Supabase signed URL for bucket: {bucket}, path: {path}")

        # Use download parameter to control Content-Disposition header
        # download=False means the file should be displayed inline (for PDFs, images, etc.)
        # download=True means the file should be downloaded
        res = supabase.storage.from_(bucket).create_signed_url(
            path,
            expires_in=3600,
            options={"download": download}
        )
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


@router.get("/video-info/{doc_id}", response_model=VideoFileInfo)
def get_video_info(
    doc_id: str,
    auth: AuthUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    """
    Get video file info by doc_id.
    Returns bucket and storage_path needed to generate signed URL for video playback.
    """
    user_id = auth.id

    # Query app_doc_meta for the video info
    resp = supabase.table("app_doc_meta").select(
        "doc_id, filename, storage_path, mime_type"
    ).eq("doc_id", doc_id).eq("user_id", user_id).single().execute()

    if not resp.data:
        raise HTTPException(404, detail="Video not found")

    data = resp.data

    # Videos are stored in the "videos" bucket
    return VideoFileInfo(
        doc_id=data["doc_id"],
        filename=data.get("filename", ""),
        bucket="videos",
        storage_path=data.get("storage_path", ""),
        mime_type=data.get("mime_type"),
    )