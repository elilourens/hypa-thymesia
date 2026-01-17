# routes/delete.py (or wherever your delete endpoint lives)

import logging
from typing import Tuple, Set, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from core.deps import get_supabase
from core.security import get_current_user, AuthUser
from data_upload.pinecone_services import delete_vectors_by_ids

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingestion"])

# In-memory store for deletion status (consider using Redis for production)
_deletion_status: Dict[str, Dict[str, Any]] = {}

@router.delete("/delete-document")
async def delete_document(
    doc_id: str = Query(..., description="The UUID of the document to delete"),
    background_tasks: BackgroundTasks = None,
    auth: AuthUser = Depends(get_current_user),
    supabase = Depends(get_supabase),
):
    """
    Delete a document (regular document or video) and all associated data.
    Runs in the background so users can continue querying while deletion happens.

    Returns immediately with status "deleting" and the doc_id.
    Use GET /ingest/delete-status/{doc_id} to check deletion progress.

    Automatically detects the document type and performs appropriate cleanup:

    For regular documents:
    - Text chunks and embeddings
    - Uploaded images and embeddings
    - Extracted deep embed images and embeddings
    - Storage files from all buckets

    For videos:
    - Video frames and embeddings (from Pinecone)
    - Video transcripts and embeddings (from Pinecone)
    - Storage files (video file, frame images)

    All database records are cleaned up via cascading deletes.
    """
    user_id = auth.id

    # Check document type
    doc_meta_result = supabase.table("app_doc_meta").select("modality").eq(
        "doc_id", doc_id
    ).eq("user_id", user_id).execute()

    if not doc_meta_result.data:
        raise HTTPException(404, detail="Document not found")

    modality = doc_meta_result.data[0].get("modality")
    logger.info(f"Queueing background deletion for document {doc_id} with modality={modality} for user {user_id}")

    # Initialize deletion status
    _deletion_status[doc_id] = {
        "status": "deleting",
        "modality": modality,
        "user_id": user_id,
        "error": None,
        "result": None
    }

    # Run deletion in background
    background_tasks.add_task(_background_delete, doc_id, modality, user_id, supabase)

    return {
        "doc_id": doc_id,
        "status": "deleting",
        "message": "Deletion started in background. Use /ingest/delete-status/{doc_id} to check progress."
    }


@router.get("/delete-status/{doc_id}")
async def get_delete_status(
    doc_id: str,
    auth: AuthUser = Depends(get_current_user),
):
    """Check the status of a background deletion."""
    if doc_id not in _deletion_status:
        raise HTTPException(404, detail="No deletion job found for this document")

    status = _deletion_status[doc_id]

    # Verify user owns this deletion job
    if status["user_id"] != auth.id:
        raise HTTPException(404, detail="No deletion job found for this document")

    return {
        "doc_id": doc_id,
        "status": status["status"],
        "error": status["error"],
        "result": status["result"]
    }


async def _background_delete(doc_id: str, modality: str, user_id: str, supabase):
    """Background task that performs the actual deletion."""
    try:
        if modality == "video":
            result = await _delete_video(doc_id=doc_id, user_id=user_id, supabase=supabase)
        else:
            result = await _delete_regular_document(doc_id=doc_id, user_id=user_id, supabase=supabase)

        _deletion_status[doc_id] = {
            **_deletion_status[doc_id],
            "status": "completed",
            "result": result
        }
        logger.info(f"Background deletion completed for doc_id={doc_id}")
    except Exception as e:
        logger.error(f"Background deletion failed for doc_id={doc_id}: {e}")
        _deletion_status[doc_id] = {
            **_deletion_status[doc_id],
            "status": "failed",
            "error": str(e)
        }


async def _delete_regular_document(doc_id: str, user_id: str, supabase):
    """Delete a regular document (text/image).

    Uses database cascade delete to automatically clean up:
    - app_chunks (cascades from app_doc_meta)
    - app_vector_registry (cascades from app_chunks)
    - app_image_tags (cascades from both app_chunks and app_doc_meta)
    """
    # Get all chunks and their vector registrations to handle external cleanup
    q = (supabase
        .table("app_vector_registry")
        .select("vector_id,app_chunks!inner(bucket,storage_path,modality)")
        .eq("app_chunks.doc_id", doc_id)
        .eq("app_chunks.user_id", user_id)
    ).execute()

    rows = q.data or []
    if not rows:
        logger.warning(f"No vectors found for document {doc_id}")

    # Separate vector IDs by modality and index
    text_ids = []
    image_ids = []
    extracted_image_ids = []
    files: Set[Tuple[str, str]] = set()

    for r in rows:
        ch = r["app_chunks"]
        bucket = ch.get("bucket")
        path = ch.get("storage_path")
        if bucket and path:
            files.add((bucket, path))

        modality = ch.get("modality")
        if modality == "text":
            text_ids.append(r["vector_id"])
        elif modality == "image":
            # Distinguish extracted images from uploaded images by bucket
            if bucket == "extracted-images":
                extracted_image_ids.append(r["vector_id"])
            else:
                image_ids.append(r["vector_id"])

    # Delete from Pinecone (3 separate indexes)
    if text_ids:
        delete_vectors_by_ids(ids=text_ids, modality="text", namespace=user_id)
    if image_ids:
        delete_vectors_by_ids(ids=image_ids, modality="image", namespace=user_id)
    if extracted_image_ids:
        delete_vectors_by_ids(ids=extracted_image_ids, modality="extracted_image", namespace=user_id)

    # Delete files from Supabase storage - batch by bucket for efficiency
    deleted_files = 0
    files_by_bucket: Dict[str, list] = {}
    for bucket, path in files:
        if bucket not in files_by_bucket:
            files_by_bucket[bucket] = []
        files_by_bucket[bucket].append(path)

    for bucket, paths in files_by_bucket.items():
        try:
            supabase.storage.from_(bucket).remove(paths)
            deleted_files += len(paths)
            logger.info(f"Deleted {len(paths)} files from {bucket}")
        except Exception as e:
            logger.error(f"Storage delete failed for {bucket}: {e}")

    # Delete from database - cascade delete automatically handles:
    # - app_chunks (via fk_chunks_doc with ON DELETE CASCADE)
    # - app_vector_registry (via fk_registry_chunk with ON DELETE CASCADE)
    # - app_image_tags (via fk_chunk and fk_doc with ON DELETE CASCADE)
    supabase.table("app_doc_meta").delete().eq(
        "doc_id", doc_id
    ).eq("user_id", user_id).execute()

    return {
        "doc_id": doc_id,
        "status": "deleted",
        "deleted_vectors": len(text_ids) + len(image_ids) + len(extracted_image_ids),
        "deleted_files": deleted_files,
        "breakdown": {
            "text_chunks": len(text_ids),
            "uploaded_images": len(image_ids),
            "extracted_images": len(extracted_image_ids),
        }
    }


async def _delete_video(doc_id: str, user_id: str, supabase):
    """Delete a video and all associated data.

    Uses database cascade delete to automatically clean up:
    - app_chunks (cascades from app_doc_meta)
    - app_vector_registry (cascades from app_chunks)
    - app_image_tags (cascades from both app_chunks and app_doc_meta)
    """

    # Import here to avoid circular dependency
    try:
        from data_upload.pinecone_services import pc, VIDEO_FRAME_INDEX_NAME, VIDEO_TRANSCRIPT_INDEX_NAME
    except ImportError:
        logger.error("Failed to import Pinecone services for video deletion")
        raise HTTPException(500, detail="Video deletion service unavailable")

    logger.info(f"Deleting video document {doc_id} for user {user_id}")

    # Get all chunks associated with this video (video file, frames, transcripts)
    chunks_result = supabase.table("app_chunks").select("bucket, storage_path, modality").eq(
        "doc_id", doc_id
    ).eq("user_id", user_id).execute()

    chunks = chunks_result.data or []
    storage_files: Set[Tuple[str, str]] = set()
    deleted_frames = 0
    deleted_transcripts = 0

    # Collect storage files and count chunk types
    for chunk in chunks:
        bucket = chunk.get("bucket")
        path = chunk.get("storage_path")
        modality = chunk.get("modality")

        if bucket and path:
            storage_files.add((bucket, path))

        if modality == "video_frame":
            deleted_frames += 1
        elif modality == "video_transcript":
            deleted_transcripts += 1

    # Delete video frame vectors from Pinecone using metadata filter
    try:
        frame_index = pc.Index(VIDEO_FRAME_INDEX_NAME)
        frame_index.delete(
            filter={"doc_id": {"$eq": doc_id}},
            namespace=user_id
        )
        logger.info(f"Deleted video frame vectors for doc_id={doc_id}")
    except Exception as e:
        logger.error(f"Error deleting video frame vectors: {e}")

    # Delete video transcript vectors from Pinecone
    try:
        transcript_index = pc.Index(VIDEO_TRANSCRIPT_INDEX_NAME)
        transcript_index.delete(
            filter={"doc_id": {"$eq": doc_id}},
            namespace=user_id
        )
        logger.info(f"Deleted video transcript vectors for doc_id={doc_id}")
    except Exception as e:
        logger.error(f"Error deleting video transcript vectors: {e}")

    # Delete storage files - batch by bucket for efficiency
    deleted_files = 0
    files_by_bucket: Dict[str, list] = {}
    for bucket, path in storage_files:
        if bucket not in files_by_bucket:
            files_by_bucket[bucket] = []
        files_by_bucket[bucket].append(path)

    for bucket, paths in files_by_bucket.items():
        try:
            supabase.storage.from_(bucket).remove(paths)
            deleted_files += len(paths)
            logger.info(f"Deleted {len(paths)} files from {bucket}")
        except Exception as e:
            logger.error(f"Storage delete failed for {bucket}: {e}")

    # Delete app_doc_meta record - cascade delete automatically handles:
    # - app_chunks (via fk_chunks_doc with ON DELETE CASCADE)
    # - app_vector_registry (via fk_registry_chunk with ON DELETE CASCADE)
    # - app_image_tags (via fk_chunk and fk_doc with ON DELETE CASCADE)
    supabase.table("app_doc_meta").delete().eq(
        "doc_id", doc_id
    ).eq("user_id", user_id).execute()

    logger.info(f"Deleted doc_meta record for {doc_id} (cascade deleted {len(chunks)} chunks)")

    return {
        "doc_id": doc_id,
        "status": "deleted",
        "deleted_frames": deleted_frames,
        "deleted_transcripts": deleted_transcripts,
        "deleted_files": deleted_files,
        "message": "Video and all associated data deleted successfully"
    }