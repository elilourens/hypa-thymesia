import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Form
from core.config import get_settings
from core.deps import get_supabase
from core.security import get_current_user, AuthUser
from data_upload.supabase_text_services import upload_text_to_bucket
from data_upload.supabase_image_services import upload_image_to_bucket
from ingestion.ingest_common import ingest_file_content

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingestion"])


@router.post("/upload-text-and-images")
async def ingest_text_and_image_files(
    file: UploadFile = File(...),
    group_id: Optional[str] = Form(None),
    extract_deep_embeds: bool = Form(True),
    auth: AuthUser = Depends(get_current_user),
    supabase = Depends(get_supabase),
    settings = Depends(get_settings),
):
    """
    Ingest a file by uploading it to storage and extracting text/images.
    """
    user_id = auth.id
    content = await file.read()
    
    logger.info(f"Upload started: {file.filename}, size: {len(content)} bytes, extract_deep_embeds: {extract_deep_embeds}")

    # --- Upload file to storage ---
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    
    try:
        # Determine storage path based on file type
        if ext in ("png", "jpeg", "jpg", "webp"):
            storage_path = upload_image_to_bucket(supabase, content, file.filename)
        else:
            storage_path = upload_text_to_bucket(
                supabase,
                content,
                file.filename,
                mime_type=file.content_type,
            )
        
        if not storage_path:
            raise HTTPException(500, detail="Failed to upload file to storage")
        
        logger.info(f"Uploaded to storage: {storage_path}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading to storage: {e}", exc_info=True)
        raise HTTPException(500, detail="Failed to upload file to storage")

    # --- Ingest file content using shared logic ---
    try:
        result = await ingest_file_content(
            file_content=content,
            filename=file.filename,
            mime_type=file.content_type,
            user_id=user_id,
            supabase=supabase,
            settings=settings,
            storage_path=storage_path,
            extract_deep_embeds=extract_deep_embeds,
            group_id=group_id,
        )
        logger.info(f"File ingestion complete: {result}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Error during ingestion: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")