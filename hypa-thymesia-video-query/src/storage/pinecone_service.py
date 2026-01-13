"""
Pinecone service for video frame and transcript embeddings.
Follows the same structure as the main hypa-thymesia backend.
"""
import os
from typing import List, Dict, Any, Optional, Literal
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

# Modality types for video system
VideoModality = Literal["video_frame", "video_transcript"]

# Environment variables
_PINECONE_KEY = os.getenv("PINECONE_API_KEY") or os.getenv("PINECONE_KEY")
if not _PINECONE_KEY:
    raise RuntimeError("Missing PINECONE_API_KEY (or PINECONE_KEY).")

# Index names for video collections
VIDEO_FRAME_INDEX_NAME = os.getenv("PINECONE_VIDEO_FRAME_INDEX_NAME", "video-frames")
VIDEO_TRANSCRIPT_INDEX_NAME = os.getenv("PINECONE_VIDEO_TRANSCRIPT_INDEX_NAME", "video-transcripts")

# Batch size for upserts
PINECONE_MAX_BATCH = int(os.getenv("PINECONE_MAX_BATCH", "100"))

# Initialize Pinecone client
pc = Pinecone(
    api_key=_PINECONE_KEY,
    environment=os.getenv("PINECONE_ENVIRONMENT") or None,
)

# Index dimensions
VIDEO_FRAME_DIM = 512  # CLIP ViT-B-32 image embeddings
VIDEO_TRANSCRIPT_DIM = 384  # sentence-transformers all-MiniLM-L6-v2

# Lazy-loaded index handles
_video_frame_index = None
_video_transcript_index = None


def _get_video_frame_index():
    """Get or create video frame index handle."""
    global _video_frame_index
    if _video_frame_index is None:
        _video_frame_index = pc.Index(VIDEO_FRAME_INDEX_NAME)
    return _video_frame_index


def _get_video_transcript_index():
    """Get or create video transcript index handle."""
    global _video_transcript_index
    if _video_transcript_index is None:
        _video_transcript_index = pc.Index(VIDEO_TRANSCRIPT_INDEX_NAME)
    return _video_transcript_index


def _get_index_for_modality(modality: VideoModality):
    """Get the appropriate index for the given modality."""
    if modality == "video_frame":
        return _get_video_frame_index()
    elif modality == "video_transcript":
        return _get_video_transcript_index()
    else:
        raise ValueError(f"Unknown modality: {modality}")


def upsert_vectors(
    *,
    vectors: List[Dict[str, Any]],
    modality: VideoModality,
    namespace: Optional[str] = None,
) -> None:
    """
    Upsert vectors to Pinecone in batches.

    Args:
        vectors: List of dicts with keys: id, values, metadata
        modality: "video_frame" or "video_transcript"
        namespace: User ID for multi-tenant isolation
    """
    index = _get_index_for_modality(modality)

    # Batch the vectors
    for i in range(0, len(vectors), PINECONE_MAX_BATCH):
        batch = vectors[i : i + PINECONE_MAX_BATCH]
        index.upsert(vectors=batch, namespace=namespace or "")


def query_vectors(
    *,
    vector: List[float],
    modality: VideoModality,
    top_k: int = 5,
    namespace: Optional[str] = None,
    metadata_filter: Optional[Dict[str, Any]] = None,
    include_metadata: bool = True,
):
    """
    Query vectors from Pinecone.

    Args:
        vector: Query embedding vector
        modality: "video_frame" or "video_transcript"
        top_k: Number of results to return
        namespace: User ID for multi-tenant isolation
        metadata_filter: Optional metadata filter (Pinecone filter syntax)
        include_metadata: Whether to include metadata in results

    Returns:
        QueryResponse with matches
    """
    index = _get_index_for_modality(modality)

    return index.query(
        vector=vector,
        top_k=top_k,
        namespace=namespace or "",
        filter=metadata_filter,
        include_metadata=include_metadata,
    )


def delete_vectors_by_ids(
    *,
    ids: List[str],
    modality: VideoModality,
    namespace: Optional[str] = None,
) -> None:
    """
    Delete vectors by IDs.

    Args:
        ids: List of vector IDs to delete
        modality: "video_frame" or "video_transcript"
        namespace: User ID for multi-tenant isolation
    """
    if not ids:
        return

    index = _get_index_for_modality(modality)
    index.delete(ids=ids, namespace=namespace or "")


def delete_by_filter(
    *,
    filter_dict: Dict[str, Any],
    modality: VideoModality,
    namespace: Optional[str] = None,
) -> None:
    """
    Delete vectors by metadata filter.

    Args:
        filter_dict: Pinecone metadata filter
        modality: "video_frame" or "video_transcript"
        namespace: User ID for multi-tenant isolation
    """
    index = _get_index_for_modality(modality)
    index.delete(filter=filter_dict, namespace=namespace or "")


def update_vectors_metadata(
    *,
    vector_ids: List[str],
    modality: VideoModality,
    namespace: Optional[str] = None,
    set_metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Update metadata for existing vectors.

    Args:
        vector_ids: List of vector IDs to update
        modality: "video_frame" or "video_transcript"
        namespace: User ID for multi-tenant isolation
        set_metadata: Metadata to set/update
    """
    if not vector_ids or not set_metadata:
        return

    index = _get_index_for_modality(modality)

    for vector_id in vector_ids:
        index.update(
            id=vector_id,
            set_metadata=set_metadata,
            namespace=namespace or "",
        )


def get_index_stats(modality: VideoModality) -> Dict[str, Any]:
    """
    Get statistics for an index.

    Args:
        modality: "video_frame" or "video_transcript"

    Returns:
        Dictionary with index statistics
    """
    index = _get_index_for_modality(modality)
    return index.describe_index_stats()
