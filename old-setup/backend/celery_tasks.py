"""Celery tasks for backend service (file ingestion, video processing, deletion)."""
import logging
import os
from celery import shared_task
from celery_app import celery_app
from ingestion.ingest_common import ingest_file_content

logger = logging.getLogger(__name__)

@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    time_limit=600,  # 10 minutes
    soft_time_limit=580,
)
def ingest_file(
    self,
    file_content: bytes,
    filename: str,
    mime_type: str,
    user_id: str,
    doc_id: str,
    storage_path: str,
    extract_deep_embeds: bool = False,
    group_id: str = None,
    enable_tagging: bool = True,
):
    """Ingest a file (text, PDF, image) and process it."""
    try:
        logger.info(f"Starting file ingestion: doc_id={doc_id}, filename={filename}")
        
        # Call the actual ingestion logic from ingest_common
        result = ingest_file_content(
            file_content=file_content,
            filename=filename,
            mime_type=mime_type,
            user_id=user_id,
            doc_id=doc_id,
            storage_path=storage_path,
            extract_deep_embeds=extract_deep_embeds,
            group_id=group_id,
            enable_tagging=enable_tagging,
        )
        
        logger.info(f"File ingestion completed: doc_id={doc_id}")
        return {"status": "completed", "doc_id": doc_id, "result": result}
        
    except Exception as exc:
        logger.error(f"File ingestion failed: doc_id={doc_id}, error={exc}", exc_info=True)
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=min(2 ** self.request.retries * 60, 600))


@celery_app.task(
    bind=True,
    max_retries=1,
    default_retry_delay=300,
    time_limit=900,  # 15 minutes
    soft_time_limit=880,
)
def ingest_video(
    self,
    file_content: bytes,
    filename: str,
    user_id: str,
    doc_id: str,
    storage_path: str,
):
    """Orchestrate video processing (send to video service via Celery)."""
    try:
        logger.info(f"Starting video ingestion: doc_id={doc_id}, filename={filename}")

        # Queue video processing task in video service queue
        # Using celery_app.send_task to avoid cross-service imports
        video_task = celery_app.send_task(
            "celery_tasks.process_video",
            kwargs={
                "file_content": file_content.hex() if isinstance(file_content, bytes) else file_content,
                "filename": filename,
                "user_id": user_id,
                "doc_id": doc_id,
            },
            queue="video_queue",
        )

        logger.info(f"Video processing queued: doc_id={doc_id}, video_task_id={video_task.id}")
        return {"status": "processing", "doc_id": doc_id, "video_task_id": video_task.id}

    except Exception as exc:
        logger.error(f"Video ingestion failed: doc_id={doc_id}, error={exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=300)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    time_limit=300,  # 5 minutes
    soft_time_limit=280,
)
def delete_document(
    self,
    doc_id: str,
    modality: str,
    user_id: str,
):
    """Delete a document and all associated vectors/files."""
    try:
        logger.info(f"Starting document deletion: doc_id={doc_id}, modality={modality}")
        
        from core.deps import get_supabase
        from data_upload.pinecone_services import delete_vectors_by_ids
        
        supabase = get_supabase()
        
        # Get all vectors associated with this document
        if modality == "text" or modality == "mixed":
            # Delete from text index
            delete_vectors_by_ids(doc_id, index_type="text")
        
        if modality == "image" or modality == "mixed":
            # Delete from image index
            delete_vectors_by_ids(doc_id, index_type="image")
        
        if modality == "video" or modality == "mixed":
            # Delete from video index
            delete_vectors_by_ids(doc_id, index_type="video")
        
        # Delete from database
        supabase.table("app_doc_meta").delete().eq("doc_id", doc_id).execute()
        supabase.table("app_text_chunks").delete().eq("doc_id", doc_id).execute()
        
        logger.info(f"Document deletion completed: doc_id={doc_id}")
        return {"status": "deleted", "doc_id": doc_id}
        
    except Exception as exc:
        logger.error(f"Document deletion failed: doc_id={doc_id}, error={exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=30)
