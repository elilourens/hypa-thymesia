"""
Two-stage tagging pipeline: CLIP filtering + OWL-ViT verification.
Orchestrates the complete auto-tagging workflow.
"""

from typing import List, Dict, Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor

from tagging.label_embedder import get_top_label_candidates
from tagging.owlvit_detector import verify_labels_in_image, get_unique_verified_labels
from core.deps import get_supabase


# Thread pool for running ML models (CPU/GPU intensive)
_executor = ThreadPoolExecutor(max_workers=2)


async def tag_image(
    chunk_id: str,
    image_embedding: List[float],
    image_bytes: bytes,
    user_id: str,
    doc_id: str,
    clip_top_k: int = 15,
    clip_min_confidence: float = 0.3,
    owlvit_min_confidence: float = 0.7,
    store_candidates: bool = False
) -> Dict[str, any]:
    """
    Run the complete two-stage tagging pipeline for an image.

    Args:
        chunk_id: Image chunk ID
        image_embedding: Pre-computed CLIP image embedding (512D)
        image_bytes: Raw image bytes
        user_id: User ID for tenant isolation
        doc_id: Document ID
        clip_top_k: Number of CLIP candidates to generate
        clip_min_confidence: Minimum CLIP confidence threshold
        owlvit_min_confidence: Minimum OWL-ViT confidence threshold
        store_candidates: Whether to store unverified CLIP candidates

    Returns:
        Dict with tagging results:
        {
            "chunk_id": str,
            "verified_tags": [...],
            "candidate_tags": [...],
            "processing_time_ms": float
        }
    """
    import time
    import logging
    logger = logging.getLogger(__name__)

    start_time = time.time()

    # Stage 1: CLIP filtering (fast)
    clip_candidates = await asyncio.get_event_loop().run_in_executor(
        _executor,
        get_top_label_candidates,
        image_embedding,
        clip_top_k,
        clip_min_confidence
    )

    logger.info(f"CLIP generated {len(clip_candidates)} candidates for chunk_id={chunk_id}")
    if clip_candidates:
        top_5 = [(c['label'], f"{c['confidence']:.2f}") for c in clip_candidates[:5]]
        logger.info(f"Top 5 CLIP candidates: {top_5}")

    if not clip_candidates:
        logger.warning(f"No CLIP candidates found for chunk_id={chunk_id}")
        return {
            "chunk_id": chunk_id,
            "verified_tags": [],
            "candidate_tags": [],
            "processing_time_ms": (time.time() - start_time) * 1000
        }

    # Extract label strings for OWL-ViT
    candidate_labels = [c["label"] for c in clip_candidates]
    logger.info(f"Sending {len(candidate_labels)} candidates to OWL-ViT: {candidate_labels}")

    # Stage 2: OWL-ViT verification (slower but precise)
    detections = await asyncio.get_event_loop().run_in_executor(
        _executor,
        verify_labels_in_image,
        image_bytes,
        candidate_labels,
        owlvit_min_confidence
    )

    logger.info(f"OWL-ViT returned {len(detections)} detections for chunk_id={chunk_id}")
    if detections:
        det_summary = [(d['label'], f"{d['confidence']:.2f}") for d in detections]
        logger.info(f"OWL-ViT detections: {det_summary}")

    # Get unique verified labels
    unique_detections = get_unique_verified_labels(detections)
    logger.info(f"Final unique verified tags: {len(unique_detections)}")

    # Store verified tags in database
    await store_tags(
        chunk_id=chunk_id,
        doc_id=doc_id,
        user_id=user_id,
        verified_tags=unique_detections,
        candidate_tags=clip_candidates if store_candidates else []
    )

    processing_time = (time.time() - start_time) * 1000

    return {
        "chunk_id": chunk_id,
        "verified_tags": unique_detections,
        "candidate_tags": clip_candidates,
        "processing_time_ms": processing_time
    }


async def store_tags(
    chunk_id: str,
    doc_id: str,
    user_id: str,
    verified_tags: List[Dict[str, any]],
    candidate_tags: List[Dict[str, any]] = None
) -> None:
    """
    Store tags in the app_image_tags table.

    Args:
        chunk_id: Image chunk ID
        doc_id: Document ID
        user_id: User ID
        verified_tags: List of OWL-ViT verified detections
        candidate_tags: Optional list of CLIP candidates to store
    """
    supabase = get_supabase()

    # Prepare tag rows
    tag_rows = []

    # Add verified tags
    for tag in verified_tags:
        tag_rows.append({
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "user_id": user_id,
            "tag_name": tag["label"],
            "confidence": tag["confidence"],
            "verified": True,
            "bbox": tag["bbox"]
        })

    # Optionally add unverified candidates
    if candidate_tags:
        for tag in candidate_tags:
            # Skip if already verified
            if any(t["label"] == tag["label"] for t in verified_tags):
                continue

            tag_rows.append({
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "user_id": user_id,
                "tag_name": tag["label"],
                "confidence": tag["confidence"],
                "verified": False,
                "bbox": None
            })

    # Batch insert tags
    if tag_rows:
        supabase.table("app_image_tags").insert(tag_rows).execute()


async def get_tags_for_chunk(chunk_id: str, user_id: str, verified_only: bool = True) -> List[Dict[str, any]]:
    """
    Retrieve tags for a specific image chunk.

    Args:
        chunk_id: Image chunk ID
        user_id: User ID for tenant isolation
        verified_only: Only return verified tags

    Returns:
        List of tag dicts
    """
    supabase = get_supabase()

    query = (
        supabase.table("app_image_tags")
        .select("*")
        .eq("chunk_id", chunk_id)
        .eq("user_id", user_id)
    )

    if verified_only:
        query = query.eq("verified", True)

    result = query.execute()

    return result.data


async def search_chunks_by_tags(
    user_id: str,
    tags: List[str],
    min_confidence: float = 0.7,
    limit: int = 50
) -> List[Dict[str, any]]:
    """
    Search for image chunks by tag names.

    Args:
        user_id: User ID for tenant isolation
        tags: List of tag names to search for
        min_confidence: Minimum confidence threshold
        limit: Maximum number of results

    Returns:
        List of chunk IDs with associated metadata
    """
    supabase = get_supabase()

    # Query tags table
    query = (
        supabase.table("app_image_tags")
        .select("chunk_id, doc_id, tag_name, confidence, bbox, app_chunks!inner(storage_path, bucket, mime_type)")
        .eq("user_id", user_id)
        .eq("verified", True)
        .gte("confidence", min_confidence)
        .in_("tag_name", tags)
        .order("confidence", desc=True)
        .limit(limit)
    )

    result = query.execute()

    return result.data


async def get_popular_tags(
    user_id: str,
    limit: int = 20,
    verified_only: bool = True
) -> List[Dict[str, any]]:
    """
    Get most frequently occurring tags for a user.

    Args:
        user_id: User ID for tenant isolation
        limit: Number of top tags to return
        verified_only: Only count verified tags

    Returns:
        List of dicts with tag_name and count
    """
    supabase = get_supabase()

    # This would ideally be a SQL aggregation query
    # For now, we'll fetch and count in Python

    query = (
        supabase.table("app_image_tags")
        .select("tag_name")
        .eq("user_id", user_id)
    )

    if verified_only:
        query = query.eq("verified", True)

    result = query.execute()

    # Count occurrences
    tag_counts = {}
    for row in result.data:
        tag = row["tag_name"]
        tag_counts[tag] = tag_counts.get(tag, 0) + 1

    # Sort by count and return top N
    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:limit]

    return [{"tag_name": tag, "count": count} for tag, count in sorted_tags]


async def delete_tags_for_chunk(chunk_id: str, user_id: str) -> None:
    """
    Delete all tags for a specific chunk.

    Args:
        chunk_id: Image chunk ID
        user_id: User ID for tenant isolation
    """
    supabase = get_supabase()

    supabase.table("app_image_tags").delete().eq("chunk_id", chunk_id).eq("user_id", user_id).execute()


async def delete_tags_for_document(doc_id: str, user_id: str) -> None:
    """
    Delete all tags for a document.

    Args:
        doc_id: Document ID
        user_id: User ID for tenant isolation
    """
    supabase = get_supabase()

    supabase.table("app_image_tags").delete().eq("doc_id", doc_id).eq("user_id", user_id).execute()
