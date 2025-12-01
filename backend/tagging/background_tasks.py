"""
Background task utilities for async image tagging.
"""

import asyncio
import logging
from typing import List

from tagging.tag_pipeline import tag_image
from core.deps import get_supabase
from data_upload.pinecone_services import query_vectors


logger = logging.getLogger(__name__)


async def tag_image_background(
    chunk_id: str,
    user_id: str,
    doc_id: str,
    image_embedding: List[float],
    storage_path: str,
    bucket: str
) -> None:
    """
    Background task to tag an image asynchronously.

    Args:
        chunk_id: Image chunk ID
        user_id: User ID
        doc_id: Document ID
        image_embedding: Pre-computed CLIP embedding
        storage_path: Path to image in Supabase storage
        bucket: Storage bucket name
    """
    try:
        logger.info(f"Starting background tagging for chunk_id={chunk_id}")

        # Download image from Supabase storage
        supabase = get_supabase()

        try:
            image_bytes = supabase.storage.from_(bucket).download(storage_path)
            logger.info(f"Downloaded image: type={type(image_bytes)}, size={len(image_bytes) if isinstance(image_bytes, bytes) else 'unknown'}")
        except Exception as e:
            logger.error(f"Failed to download image {storage_path} from bucket {bucket}: {e}")
            return

        # Run tagging pipeline with lower thresholds for better recall
        result = await tag_image(
            chunk_id=chunk_id,
            image_embedding=image_embedding,
            image_bytes=image_bytes,
            user_id=user_id,
            doc_id=doc_id,
            clip_min_confidence=0.15,  # Lower threshold to get more candidates for OWL-ViT
            owlvit_min_confidence=0.15,  # Lower threshold for OWL-ViT
            store_candidates=False  # Only store OWL-ViT verified tags
        )

        logger.info(
            f"Tagging complete for chunk_id={chunk_id}: "
            f"{len(result['verified_tags'])} verified tags in "
            f"{result['processing_time_ms']:.0f}ms"
        )

    except Exception as e:
        logger.error(f"Error in background tagging for chunk_id={chunk_id}: {e}", exc_info=True)


async def tag_uploaded_image_after_ingest(
    doc_id: str,
    user_id: str,
    image_embedding: List[float],
    file_bytes: bytes
) -> None:
    """
    Tag a newly uploaded image after ingestion completes.

    This is called from the ingest_common.py flow.

    Args:
        doc_id: Document ID (same as chunk_id for single images)
        user_id: User ID
        image_embedding: Pre-computed CLIP embedding
        file_bytes: Raw image bytes
    """
    try:
        logger.info(f"Starting post-upload tagging for doc_id={doc_id}")

        # Fetch chunk_id from database (for single images, there should be one chunk)
        supabase = get_supabase()

        chunk_result = (
            supabase.table("app_chunks")
            .select("chunk_id, storage_path, bucket")
            .eq("doc_id", doc_id)
            .eq("user_id", user_id)
            .eq("modality", "image")
            .execute()
        )

        if not chunk_result.data:
            logger.warning(f"No image chunks found for doc_id={doc_id}")
            return

        chunk = chunk_result.data[0]
        chunk_id = chunk["chunk_id"]

        # Run tagging pipeline with lower thresholds for better recall
        result = await tag_image(
            chunk_id=chunk_id,
            image_embedding=image_embedding,
            image_bytes=file_bytes,
            user_id=user_id,
            doc_id=doc_id,
            clip_min_confidence=0.15,  # Lowered from default 0.3
            owlvit_min_confidence=0.15,  # Lowered from default 0.7 for testing
            store_candidates=False
        )

        logger.info(
            f"Post-upload tagging complete for doc_id={doc_id}: "
            f"{len(result['verified_tags'])} verified tags"
        )

    except Exception as e:
        logger.error(f"Error in post-upload tagging for doc_id={doc_id}: {e}", exc_info=True)


def schedule_tagging_task(coro):
    """
    Schedule a coroutine to run in the background without blocking.

    Args:
        coro: Coroutine to run
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If event loop is running, create a task
            asyncio.create_task(coro)
        else:
            # If no event loop, run until complete
            loop.run_until_complete(coro)
    except RuntimeError:
        # Create new event loop if none exists
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(coro)
