import logging
import os
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, Form
from core.config import get_settings
from core.deps import get_supabase
from core.security import get_current_user, AuthUser
from core.user_limits import check_user_can_upload, ensure_user_settings_exist
from data_upload.supabase_text_services import upload_text_to_bucket
from data_upload.supabase_image_services import upload_image_to_bucket
from ingestion.ingest_common import ingest_file_content

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingestion"])
USE_CELERY = os.getenv("USE_CELERY", "false").lower() == "true"


async def process_file_background(
    file_content: bytes,
    filename: str,
    mime_type: str,
    user_id: str,
    doc_id: str,
    storage_path: str,
    extract_deep_embeds: bool,
    group_id: Optional[str],
    enable_tagging: bool,
):
    """
    Background task to process file ingestion.
    This runs asynchronously after the API returns to the user.
    """
    from core.deps import get_supabase
    from core.config import get_settings

    supabase = get_supabase()
    settings = get_settings()

    try:
        # Update status to processing
        supabase.table("app_doc_meta").update({
            "processing_status": "processing"
        }).eq("doc_id", doc_id).execute()

        logger.info(f"Background processing started: {filename} (doc_id={doc_id})")

        # Process the file
        result = await ingest_file_content(
            file_content=file_content,
            filename=filename,
            mime_type=mime_type,
            user_id=user_id,
            supabase=supabase,
            settings=settings,
            storage_path=storage_path,
            extract_deep_embeds=extract_deep_embeds,
            group_id=group_id,
            enable_tagging=enable_tagging,
            doc_id=doc_id,  # Pass doc_id to use existing record
        )

        # Update status to completed
        supabase.table("app_doc_meta").update({
            "processing_status": "completed",
            "text_chunks_count": result.get("text_chunks_ingested", 0),
            "images_count": result.get("images_extracted", 0),
        }).eq("doc_id", doc_id).execute()

        logger.info(f"Background processing completed: {filename} (doc_id={doc_id})")

    except Exception as e:
        logger.error(f"Background processing failed for {filename} (doc_id={doc_id}): {e}", exc_info=True)

        # Update status to failed
        try:
            supabase.table("app_doc_meta").update({
                "processing_status": "failed",
                "error_message": str(e)[:500]  # Limit error message length
            }).eq("doc_id", doc_id).execute()
        except Exception as update_error:
            logger.error(f"Failed to update error status: {update_error}")


@router.post("/upload-text-and-images")
async def ingest_text_and_image_files(
    file: UploadFile = File(...),
    group_id: Optional[str] = Form(None),
    extract_deep_embeds: bool = Form(True),
    enable_tagging: bool = Form(True),
    background_tasks: BackgroundTasks = None,
    auth: AuthUser = Depends(get_current_user),
    supabase = Depends(get_supabase),
    settings = Depends(get_settings),
):
    """
    Ingest a file by uploading it to storage and processing in background.
    Returns immediately with doc_id and status='processing'.
    """
    user_id = auth.id

    # Ensure user settings exist
    ensure_user_settings_exist(supabase, user_id)

    # Check if user can upload (raises HTTPException if limit reached)
    check_user_can_upload(supabase, user_id)

    content = await file.read()

    logger.debug(f"Upload started: {file.filename}, size: {len(content)} bytes, extract_deep_embeds: {extract_deep_embeds}")

    # Generate doc_id upfront
    doc_id = str(uuid4())
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""

    # --- Upload file to storage FIRST (fast operation) ---
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

        logger.debug(f"Uploaded to storage: {storage_path}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading to storage: {e}", exc_info=True)
        raise HTTPException(500, detail="Failed to upload file to storage")

    # --- Create doc_meta record with 'queued' status ---
    try:
        from utils.db_helpers import ensure_doc_meta
        ensure_doc_meta(supabase, user_id=user_id, doc_id=doc_id, group_id=group_id)

        # Update with initial status and filename
        supabase.table("app_doc_meta").update({
            "processing_status": "queued",
            "filename": file.filename,
            "mime_type": file.content_type,
            "storage_path": storage_path,
        }).eq("doc_id", doc_id).execute()

        logger.info(f"Created doc_meta record: doc_id={doc_id}, status=queued")
    except Exception as e:
        logger.error(f"Error creating doc_meta: {e}", exc_info=True)
        raise HTTPException(500, detail="Failed to create document record")

    # --- Queue processing via Celery or BackgroundTasks ---
    task_id = None
    if USE_CELERY:
        from celery_tasks import ingest_file
        task = ingest_file.delay(
            file_content=content,
            filename=file.filename,
            mime_type=file.content_type,
            user_id=user_id,
            doc_id=doc_id,
            storage_path=storage_path,
            extract_deep_embeds=extract_deep_embeds,
            group_id=group_id,
            enable_tagging=enable_tagging,
        )
        task_id = task.id
        # Update doc_meta with Celery task ID
        supabase.table("app_doc_meta").update({
            "celery_task_id": task_id,
        }).eq("doc_id", doc_id).execute()
        logger.info(f"Queued Celery file processing: {file.filename} (doc_id={doc_id}, task_id={task_id})")
    elif background_tasks:
        background_tasks.add_task(
            process_file_background,
            file_content=content,
            filename=file.filename,
            mime_type=file.content_type,
            user_id=user_id,
            doc_id=doc_id,
            storage_path=storage_path,
            extract_deep_embeds=extract_deep_embeds,
            group_id=group_id,
            enable_tagging=enable_tagging,
        )
        logger.info(f"Queued background processing: {file.filename} (doc_id={doc_id})")
    else:
        # Fallback: process synchronously if BackgroundTasks not available
        logger.warning("BackgroundTasks not available, processing synchronously")
        await process_file_background(
            file_content=content,
            filename=file.filename,
            mime_type=file.content_type,
            user_id=user_id,
            doc_id=doc_id,
            storage_path=storage_path,
            extract_deep_embeds=extract_deep_embeds,
            group_id=group_id,
            enable_tagging=enable_tagging,
        )

    # --- Return immediately ---
    return {
        "doc_id": doc_id,
        "status": "queued",
        "message": "File uploaded successfully. Processing in background.",
        "filename": file.filename,
        "storage_path": storage_path,
        "task_id": task_id,
    }


@router.get("/processing-status/{doc_id}")
async def get_processing_status(
    doc_id: str,
    auth: AuthUser = Depends(get_current_user),
    supabase = Depends(get_supabase),
):
    """
    Get the processing status of a document.
    Returns status (queued, processing, completed, failed) and additional metadata.

    For videos: includes long_running indicator if processing takes >2 minutes.
    Frontend should poll every 30 seconds for videos and show "this might take a while" message.
    """
    user_id = auth.id
    use_celery = os.getenv("USE_CELERY", "false").lower() == "true"

    try:
        # Query doc_meta for status
        response = supabase.table("app_doc_meta").select(
            "doc_id, processing_status, filename, text_chunks_count, images_count, error_message, modality, celery_task_id"
        ).eq("doc_id", doc_id).eq("user_id", user_id).execute()

        if not response.data or len(response.data) == 0:
            raise HTTPException(status_code=404, detail="Document not found")

        doc_meta = response.data[0]
        status = doc_meta.get("processing_status", "unknown")

        # Check Celery task state if USE_CELERY and task_id exists
        if use_celery and doc_meta.get("celery_task_id"):
            from celery_app import celery_app
            task_id = doc_meta["celery_task_id"]
            task = celery_app.AsyncResult(task_id)

            # Map Celery states to our status values
            celery_state_map = {
                "PENDING": "queued",
                "STARTED": "processing",
                "SUCCESS": "completed",
                "FAILURE": "failed",
                "RETRY": "processing",
            }
            celery_status = celery_state_map.get(task.state, status)

            # Prefer Celery state over database state for accuracy
            if task.state in celery_state_map:
                status = celery_status

        return {
            "doc_id": doc_meta["doc_id"],
            "status": status,
            "filename": doc_meta.get("filename"),
            "text_chunks_count": doc_meta.get("text_chunks_count", 0),
            "images_count": doc_meta.get("images_count", 0),
            "error_message": doc_meta.get("error_message"),
            "modality": doc_meta.get("modality", "text"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting processing status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get processing status")