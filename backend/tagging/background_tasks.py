"""
Background task utilities for async image and document tagging.
"""

import asyncio
import logging
from typing import List, Optional

from tagging.tag_pipeline import tag_image
from tagging.document_tagger import get_document_tagger
from core.deps import get_supabase


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


async def tag_document_background(
    chunk_id: str,
    user_id: str,
    doc_id: str,
    text_content: str,
    filename: str = ""
) -> None:
    """
    Background task to tag a text document asynchronously.

    Args:
        chunk_id: Text chunk ID
        user_id: User ID
        doc_id: Document ID
        text_content: Full text content of the chunk
        filename: Original filename (for context)
    """
    try:
        logger.info(f"Starting background document tagging for chunk_id={chunk_id}")

        # Get document tagger
        tagger = get_document_tagger()

        # Run tagging pipeline
        result = await tagger.tag_document(
            text_content=text_content,
            filename=filename,
            min_confidence=0.5  # Only store tags with 50%+ confidence
        )

        if "error" in result:
            logger.error(f"Document tagging failed for chunk_id={chunk_id}: {result['error']}")
            return

        # Store tags in database
        stored_count = await tagger.store_document_tags(
            chunk_id=chunk_id,
            doc_id=doc_id,
            user_id=user_id,
            tags=result["tags"]
        )

        logger.info(
            f"Document tagging complete for chunk_id={chunk_id}: "
            f"{stored_count} tags stored in {result['processing_time_ms']:.0f}ms"
        )

    except Exception as e:
        logger.error(f"Error in background document tagging for chunk_id={chunk_id}: {e}", exc_info=True)


async def tag_document_after_ingest(
    doc_id: str,
    user_id: str,
    filename: str = "",
    text_chunks: Optional[List[str]] = None
) -> None:
    """
    Tag a document ONCE after ingestion completes.

    This combines all text chunks from the document and generates tags
    for the entire document, not individual chunks.

    Args:
        doc_id: Document ID
        user_id: User ID
        filename: Original filename (for context)
        text_chunks: Optional list of text chunks (if already available, avoids Pinecone query)
    """
    try:
        logger.info(f"Starting post-upload document tagging for doc_id={doc_id}")

        # Use provided text chunks if available, otherwise fetch from Pinecone
        if text_chunks:
            logger.info(f"Using {len(text_chunks)} text chunks provided directly")
            full_text_parts = text_chunks
        else:
            logger.info("No text chunks provided, fetching from Pinecone")

            # Fetch all text chunks from database
            supabase = get_supabase()

            chunk_result = (
                supabase.table("app_chunks")
                .select("chunk_id, storage_path, bucket")
                .eq("doc_id", doc_id)
                .eq("user_id", user_id)
                .eq("modality", "text")
                .order("chunk_index")
                .execute()
            )

            if not chunk_result.data:
                logger.warning(f"No text chunks found for doc_id={doc_id}")
                return

            logger.info(f"Found {len(chunk_result.data)} text chunks for doc_id={doc_id}")

            # Fetch text content from Pinecone (where the actual extracted text is stored)
            full_text_parts = []
            for chunk in chunk_result.data:
                chunk_id = chunk["chunk_id"]

                try:
                    # Query Pinecone to get the text content from metadata
                    from data_upload.pinecone_services import query_vectors

                    vector_result = await query_vectors(
                        query_embedding=None,  # Not used for ID-based lookup
                        namespace=user_id,
                        top_k=1,
                        filter={"chunk_id": chunk_id},
                        index_type="text"
                    )

                    if vector_result and "matches" in vector_result and vector_result["matches"]:
                        match = vector_result["matches"][0]
                        text_content = match.get("metadata", {}).get("text", "")

                        if text_content:
                            full_text_parts.append(text_content)
                        else:
                            logger.warning(f"No text found in Pinecone metadata for chunk_id={chunk_id}")
                    else:
                        logger.warning(f"No Pinecone match found for chunk_id={chunk_id}")

                except Exception as e:
                    logger.error(f"Error fetching text from Pinecone for chunk {chunk_id}: {e}")
                    continue

        if not full_text_parts:
            logger.error(f"Could not read any text chunks for doc_id={doc_id}")
            return

        # Combine all text with newlines
        full_document_text = "\n".join(full_text_parts)
        logger.info(f"Combined document text: {len(full_document_text)} characters")

        # Get document tagger
        tagger = get_document_tagger()

        # Run tagging pipeline on the FULL document (not per chunk)
        result = await tagger.tag_document(
            text_content=full_document_text,
            filename=filename,
            min_confidence=0.5
        )

        if "error" in result:
            logger.error(f"Document tagging failed for doc_id={doc_id}: {result['error']}")
            return

        # Store tags ONCE for the entire document (not per chunk!)
        stored_count = await tagger.store_document_tags(
            doc_id=doc_id,
            user_id=user_id,
            tags=result["tags"]
        )

        logger.info(
            f"Document tagging complete for doc_id={doc_id}: "
            f"{stored_count} tags stored (analyzed {result['preview_chars']} chars)"
        )

    except Exception as e:
        logger.error(f"Error in post-upload document tagging for doc_id={doc_id}: {e}", exc_info=True)


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
