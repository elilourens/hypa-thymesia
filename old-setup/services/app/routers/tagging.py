"""
Tagging API endpoints for the microservice.
Handles both document (LLM) and image (CLIP + OWL-ViT) tagging.
"""

import asyncio
import base64
import logging
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException

from app.schemas.formatting import (
    # Document tagging
    TagDocumentRequest,
    TagDocumentResponse,
    BatchTagDocRequest,
    BatchTagDocResponse,
    DocTagResult,
    DocumentTag,
    # Image tagging
    TagImageRequest,
    TagImageResponse,
    BatchTagImageRequest,
    BatchTagImageResponse,
    ImageTagResult,
    ImageTag,
    BoundingBox,
)
from app.services.document_tagger import get_document_tagger
from app.services.image_tagger import tag_image as run_image_tagging
from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tagging", tags=["tagging"])

# Thread pool for CPU/GPU intensive operations
_executor = ThreadPoolExecutor(max_workers=4)


# ============================================================================
# Document Tagging Endpoints
# ============================================================================

@router.post("/tag-document", response_model=TagDocumentResponse)
async def tag_single_document(req: TagDocumentRequest):
    """
    Tag a single document using Ollama LLM.

    Args:
        req: Request containing text content and optional filename

    Returns:
        Document tags with confidence scores
    """
    logger.info(f"Tagging document of length {len(req.text_content)}")

    try:
        tagger = get_document_tagger()

        # Run tagging in executor to not block event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor,
            tagger.tag_document,
            req.text_content,
            req.filename,
            req.min_confidence
        )

        if "error" in result:
            logger.warning(f"Tagging returned error: {result['error']}")
            return TagDocumentResponse(
                tags=[],
                processing_time_ms=result["processing_time_ms"],
                preview_chars=result["preview_chars"],
                total_chars=result["total_chars"],
                total_tags=0,
                filtered_tags=0,
                success=False,
                error=result["error"]
            )

        # Convert tags to response format
        tags = [
            DocumentTag(
                tag_name=t.tag_name,
                category=t.category,
                confidence=t.confidence,
                reasoning=t.reasoning
            )
            for t in result["tags"]
        ]

        logger.info(f"Successfully tagged document ({len(tags)} tags)")
        return TagDocumentResponse(
            tags=tags,
            processing_time_ms=result["processing_time_ms"],
            preview_chars=result["preview_chars"],
            total_chars=result["total_chars"],
            total_tags=result["total_tags"],
            filtered_tags=result["filtered_tags"],
            success=True
        )

    except Exception as e:
        logger.error(f"Failed to tag document: {e}", exc_info=True)
        return TagDocumentResponse(
            tags=[],
            processing_time_ms=0,
            preview_chars=0,
            total_chars=len(req.text_content),
            total_tags=0,
            filtered_tags=0,
            success=False,
            error=str(e)
        )


@router.post("/batch-tag-documents", response_model=BatchTagDocResponse)
async def batch_tag_documents(req: BatchTagDocRequest):
    """
    Tag multiple documents concurrently.

    Args:
        req: Request containing list of documents

    Returns:
        Batch tagging results
    """
    logger.info(f"Batch tagging {len(req.documents)} documents")

    settings = get_settings()
    max_concurrent = req.max_concurrent or settings.OLLAMA_NUM_PARALLEL

    tagger = get_document_tagger()
    semaphore = asyncio.Semaphore(max_concurrent)

    async def tag_single(doc_data: dict) -> DocTagResult:
        """Tag a single document with semaphore limiting."""
        doc_id = doc_data.get("doc_id", "unknown")
        text_content = doc_data.get("text_content", "")
        filename = doc_data.get("filename", "")

        if not text_content:
            return DocTagResult(
                doc_id=doc_id,
                tags=[],
                processing_time_ms=0,
                success=False,
                error="Empty text content provided"
            )

        async with semaphore:
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    _executor,
                    tagger.tag_document,
                    text_content,
                    filename,
                    req.min_confidence
                )

                if "error" in result:
                    return DocTagResult(
                        doc_id=doc_id,
                        tags=[],
                        processing_time_ms=result["processing_time_ms"],
                        success=False,
                        error=result["error"]
                    )

                tags = [
                    DocumentTag(
                        tag_name=t.tag_name,
                        category=t.category,
                        confidence=t.confidence,
                        reasoning=t.reasoning
                    )
                    for t in result["tags"]
                ]

                return DocTagResult(
                    doc_id=doc_id,
                    tags=tags,
                    processing_time_ms=result["processing_time_ms"],
                    success=True
                )

            except Exception as e:
                logger.error(f"Failed to tag doc {doc_id}: {e}")
                return DocTagResult(
                    doc_id=doc_id,
                    tags=[],
                    processing_time_ms=0,
                    success=False,
                    error=str(e)
                )

    # Execute all tagging tasks concurrently
    results = await asyncio.gather(*[
        tag_single(doc) for doc in req.documents
    ])

    successful_count = sum(1 for r in results if r.success)
    failed_count = len(results) - successful_count

    logger.info(f"Batch tagging complete: {successful_count} successful, {failed_count} failed")

    return BatchTagDocResponse(
        total_documents=len(results),
        successful=successful_count,
        failed=failed_count,
        results=results
    )


# ============================================================================
# Image Tagging Endpoints
# ============================================================================

@router.post("/tag-image", response_model=TagImageResponse)
async def tag_single_image(req: TagImageRequest):
    """
    Tag a single image using CLIP + OWL-ViT pipeline.

    Args:
        req: Request containing image embedding and base64-encoded image

    Returns:
        Verified and candidate image tags
    """
    logger.info("Tagging single image")

    try:
        # Decode base64 image
        try:
            image_bytes = base64.b64decode(req.image_base64)
        except Exception as e:
            return TagImageResponse(
                verified_tags=[],
                candidate_tags=[],
                processing_time_ms=0,
                success=False,
                error=f"Invalid base64 image: {e}"
            )

        # Run tagging in executor
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor,
            run_image_tagging,
            req.image_embedding,
            image_bytes,
            req.clip_top_k,
            req.clip_min_confidence,
            req.owlvit_min_confidence
        )

        # Convert to response format
        verified_tags = [
            ImageTag(
                label=t["label"],
                confidence=t["confidence"],
                bbox=BoundingBox(**t["bbox"]) if t.get("bbox") else None,
                verified=True
            )
            for t in result.verified_tags
        ]

        candidate_tags = [
            ImageTag(
                label=t["label"],
                confidence=t["confidence"],
                verified=False
            )
            for t in result.candidate_tags
        ]

        logger.info(f"Successfully tagged image ({len(verified_tags)} verified, {len(candidate_tags)} candidates)")
        return TagImageResponse(
            verified_tags=verified_tags,
            candidate_tags=candidate_tags,
            processing_time_ms=result.processing_time_ms,
            success=True
        )

    except Exception as e:
        logger.error(f"Failed to tag image: {e}", exc_info=True)
        return TagImageResponse(
            verified_tags=[],
            candidate_tags=[],
            processing_time_ms=0,
            success=False,
            error=str(e)
        )


@router.post("/batch-tag-images", response_model=BatchTagImageResponse)
async def batch_tag_images(req: BatchTagImageRequest):
    """
    Tag multiple images concurrently.

    Args:
        req: Request containing list of images

    Returns:
        Batch tagging results
    """
    logger.info(f"Batch tagging {len(req.images)} images")

    max_concurrent = req.max_concurrent or 4
    semaphore = asyncio.Semaphore(max_concurrent)

    async def tag_single(img_data: dict) -> ImageTagResult:
        """Tag a single image with semaphore limiting."""
        image_id = img_data.get("image_id", "unknown")
        image_embedding = img_data.get("image_embedding", [])
        image_base64 = img_data.get("image_base64", "")

        if not image_embedding or not image_base64:
            return ImageTagResult(
                image_id=image_id,
                verified_tags=[],
                candidate_tags=[],
                processing_time_ms=0,
                success=False,
                error="Missing image embedding or base64 data"
            )

        async with semaphore:
            try:
                # Decode base64 image
                image_bytes = base64.b64decode(image_base64)

                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    _executor,
                    run_image_tagging,
                    image_embedding,
                    image_bytes,
                    req.clip_top_k,
                    req.clip_min_confidence,
                    req.owlvit_min_confidence
                )

                verified_tags = [
                    ImageTag(
                        label=t["label"],
                        confidence=t["confidence"],
                        bbox=BoundingBox(**t["bbox"]) if t.get("bbox") else None,
                        verified=True
                    )
                    for t in result.verified_tags
                ]

                candidate_tags = [
                    ImageTag(
                        label=t["label"],
                        confidence=t["confidence"],
                        verified=False
                    )
                    for t in result.candidate_tags
                ]

                return ImageTagResult(
                    image_id=image_id,
                    verified_tags=verified_tags,
                    candidate_tags=candidate_tags,
                    processing_time_ms=result.processing_time_ms,
                    success=True
                )

            except Exception as e:
                logger.error(f"Failed to tag image {image_id}: {e}")
                return ImageTagResult(
                    image_id=image_id,
                    verified_tags=[],
                    candidate_tags=[],
                    processing_time_ms=0,
                    success=False,
                    error=str(e)
                )

    # Execute all tagging tasks concurrently
    results = await asyncio.gather(*[
        tag_single(img) for img in req.images
    ])

    successful_count = sum(1 for r in results if r.success)
    failed_count = len(results) - successful_count

    logger.info(f"Batch image tagging complete: {successful_count} successful, {failed_count} failed")

    return BatchTagImageResponse(
        total_images=len(results),
        successful=successful_count,
        failed=failed_count,
        results=results
    )
