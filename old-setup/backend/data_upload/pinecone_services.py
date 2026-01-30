# data_upload/pinecone_services.py

import os
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime
from dotenv import load_dotenv
from pinecone import Pinecone  # pinecone>=5

# -------------------- Config --------------------
load_dotenv()

_PINECONE_KEY = os.getenv("PINECONE_API_KEY") or os.getenv("PINECONE_KEY")
if not _PINECONE_KEY:
    raise RuntimeError("Missing PINECONE_API_KEY (or PINECONE_KEY).")

pc = Pinecone(
    api_key=_PINECONE_KEY,
    environment=os.getenv("PINECONE_ENVIRONMENT") or None,
)

TEXT_INDEX_NAME = os.getenv("PINECONE_TEXT_INDEX_NAME")
IMAGE_INDEX_NAME = os.getenv("PINECONE_IMAGE_INDEX_NAME")
EXTRACTED_IMAGE_INDEX_NAME = os.getenv("PINECONE_EXTRACTED_IMAGE_INDEX_NAME")  # NEW
VIDEO_FRAME_INDEX_NAME = os.getenv("PINECONE_VIDEO_FRAME_INDEX_NAME", "video-frames")
VIDEO_TRANSCRIPT_INDEX_NAME = os.getenv("PINECONE_VIDEO_TRANSCRIPT_INDEX_NAME", "video-transcripts")

if not TEXT_INDEX_NAME:
    raise RuntimeError("Missing PINECONE_TEXT_INDEX_NAME.")
if not IMAGE_INDEX_NAME:
    raise RuntimeError("Missing PINECONE_IMAGE_INDEX_NAME.")
if not EXTRACTED_IMAGE_INDEX_NAME:
    raise RuntimeError("Missing PINECONE_EXTRACTED_IMAGE_INDEX_NAME.")

# Lazy init: create Index handles (deferred until first use to avoid startup failures)
_text_index = None
_image_index = None
_extracted_image_index = None
_video_frame_index = None
_video_transcript_index = None

def _get_text_index():
    global _text_index
    if _text_index is None:
        _text_index = pc.Index(TEXT_INDEX_NAME)
    return _text_index

def _get_image_index():
    global _image_index
    if _image_index is None:
        _image_index = pc.Index(IMAGE_INDEX_NAME)
    return _image_index

def _get_extracted_image_index():
    global _extracted_image_index
    if _extracted_image_index is None:
        _extracted_image_index = pc.Index(EXTRACTED_IMAGE_INDEX_NAME)
    return _extracted_image_index

def _get_video_frame_index():
    global _video_frame_index
    if _video_frame_index is None:
        _video_frame_index = pc.Index(VIDEO_FRAME_INDEX_NAME)
    return _video_frame_index

def _get_video_transcript_index():
    global _video_transcript_index
    if _video_transcript_index is None:
        _video_transcript_index = pc.Index(VIDEO_TRANSCRIPT_INDEX_NAME)
    return _video_transcript_index

# Model dims
TEXT_DIM = 384          # all-MiniLM-L12-v2
IMAGE_TEXT_DIM = 512    # clip-ViT-B-32 (text+image)
VIDEO_FRAME_DIM = 512   # CLIP ViT-B-32 for video frames
VIDEO_TRANSCRIPT_DIM = 384  # all-MiniLM-L6-v2 for transcripts

MAX_BATCH = int(os.getenv("PINECONE_MAX_BATCH", "100"))

Modality = Literal["text", "image", "clip_text", "extracted_image", "video_frame", "video_transcript"] 

# -------------------- Utilities --------------------
def _chunked(xs: list, n: int):
    for i in range(0, len(xs), n):
        yield xs[i:i+n]


def _index_for_modality(modality: Modality):
    if modality == "text":
        return _get_text_index(), TEXT_DIM
    # Both CLIP-image and CLIP-text embeddings live in the same 512-D space
    if modality in ("image", "clip_text"):
        return _get_image_index(), IMAGE_TEXT_DIM
    if modality == "extracted_image":  # NEW
        return _get_extracted_image_index(), IMAGE_TEXT_DIM
    if modality == "video_frame":
        return _get_video_frame_index(), VIDEO_FRAME_DIM
    if modality == "video_transcript":
        return _get_video_transcript_index(), VIDEO_TRANSCRIPT_DIM
    raise ValueError(f"Unknown modality: {modality}")

def build_vector_item(*, vector_id: str, values: List[float], metadata: Dict[str, Any]) -> Dict[str, Any]:
    md = dict(metadata or {})
    md.setdefault("server_upserted_at", datetime.utcnow().isoformat() + "Z")
    return {"id": vector_id, "values": values, "metadata": md}

def _guard_dims(values: List[float], expected_dim: int, *, vector_id: Optional[str] = None, modality: Optional[str] = None):
    if len(values) != expected_dim:
        tag = f" (id={vector_id})" if vector_id else ""
        mod = f" for modality={modality}" if modality else ""
        raise ValueError(f"Embedding dim mismatch{mod}{tag}: got {len(values)}, expected {expected_dim}.")

# -------------------- Public API --------------------
def upsert_vectors(
    *,
    vectors: List[Dict[str, Any]],
    modality: Modality,
    namespace: Optional[str] = None,
) -> None:
    """
    Upsert to the correct index based on modality.
    Each vector dict must have keys: id, values, metadata (optional).
    """
    if not vectors:
        return

    index, expected_dim = _index_for_modality(modality)

    # Dimension guard per item
    for v in vectors:
        _guard_dims(v["values"], expected_dim, vector_id=v.get("id"), modality=modality)

    bsz = max(1, min(MAX_BATCH, len(vectors)))
    for batch in _chunked(vectors, bsz):
        index.upsert(vectors=batch, namespace=namespace)

def delete_vectors_by_ids(
    *,
    ids: List[str],
    modality: Modality,
    namespace: Optional[str] = None,
) -> None:
    if not ids:
        return
    index, _ = _index_for_modality(modality)
    index.delete(ids=ids, namespace=namespace)

def query_vectors(
    *,
    vector: List[float],
    modality: Modality,
    top_k: int = 1,
    namespace: Optional[str] = None,
    metadata_filter: Optional[Dict[str, Any]] = None,
    include_metadata: bool = True,
):
    """
    Query the correct index. You MUST pass the modality that produced the vector.
    - modality="text" for all-MiniLM-L12-v2
    - modality="image" for CLIP image embeddings
    - modality="clip_text" for CLIP text embeddings
    - modality="extracted_image" for extracted deep embed images
    """
    index, expected_dim = _index_for_modality(modality)
    _guard_dims(vector, expected_dim, modality=modality)

    return index.query(
        vector=vector,
        top_k=top_k,
        namespace=namespace,
        filter=metadata_filter,
        include_metadata=include_metadata,
    )

def update_vectors_metadata(
    *,
    vector_ids: List[str],
    modality: Modality,
    namespace: Optional[str] = None,
    set_metadata: Optional[Dict[str, Any]] = None,
    delete_keys: Optional[List[str]] = None,
) -> None:
    """
    Update or delete metadata on existing vectors WITHOUT re-upserting values.

    Pinecone v5 has per-id update. We loop IDs to apply:
      - set_metadata: dict of keys to set/overwrite
      - delete_keys: list of keys to remove
    """
    if not vector_ids:
        return
    index, _ = _index_for_modality(modality)
    ns = namespace
    for vid in vector_ids:
        if set_metadata:
            index.update(id=vid, set_metadata=set_metadata, namespace=ns)
        if delete_keys:
            index.update(id=vid, delete_metadata=delete_keys, namespace=ns)

def keyword_search_text(
    *,
    keywords: str,
    top_k: int = 10,
    namespace: Optional[str] = None,
    metadata_filter: Optional[Dict[str, Any]] = None,
):
    """
    Perform keyword search on text chunks using Pinecone's fetch_by_metadata API.

    Uses Pinecone's early-access fetch_by_metadata endpoint to retrieve vectors
    by metadata filters only, then filters by exact keyword matches.

    Args:
        keywords: Search keywords (will be matched case-insensitive in text field)
        top_k: Number of results to return
        namespace: User namespace
        metadata_filter: Additional metadata filters (e.g., group_id)

    Returns:
        Query result object with matches containing keyword-matched chunks
    """
    import requests
    import logging
    logger = logging.getLogger(__name__)

    # Get index host using describe_index
    index_info = pc.describe_index(TEXT_INDEX_NAME)
    index_host = index_info.host  # e.g., "myindex-abc123.svc.us-east1-gcp.pinecone.io"

    # Build fetch_by_metadata request
    # Fetch more than needed since we'll filter by keywords
    fetch_limit = min(top_k * 100, 10000)

    headers = {
        "Api-Key": _PINECONE_KEY,
        "Content-Type": "application/json",
        "X-Pinecone-API-Version": "2024-07"  # Required for pinecone-client>=5.x
    }

    body = {
        "limit": fetch_limit
    }

    if namespace:
        body["namespace"] = namespace

    # fetch_by_metadata requires a filter - use modality=text as base filter
    # and merge with any user-provided metadata_filter
    base_filter = {"modality": {"$eq": "text"}}

    if metadata_filter:
        # Combine filters using $and
        body["filter"] = {"$and": [base_filter, metadata_filter]}
    else:
        body["filter"] = base_filter

    logger.info(f"[Keyword Search] Fetching from Pinecone using fetch_by_metadata API (host={index_host}, filter={body['filter']})")

    # Make direct API call to fetch_by_metadata
    try:
        response = requests.post(
            f"https://{index_host}/vectors/fetch_by_metadata",
            headers=headers,
            json=body,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.HTTPError as e:
        logger.error(f"[Keyword Search] HTTP error: {e.response.status_code} - {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"[Keyword Search] Request failed: {e}")
        raise

    # Extract vectors from response
    # Response format is a dict of vectors: {"vectors": {"id1": {...}, "id2": {...}}}
    vector_dict = data.get("vectors", {})
    vectors = list(vector_dict.values()) if vector_dict else []

    logger.info(f"[Keyword Search] Received {len(vectors)} vectors from fetch_by_metadata")

    # Filter results by keyword matches in the 'text' field
    keywords_lower = keywords.lower().strip()
    keyword_terms = keywords_lower.split()

    matched_results = []
    for vector in vectors:
        metadata = vector.get("metadata", {})
        text_content = metadata.get("text", "")

        if not text_content:
            continue

        text_lower = text_content.lower()

        # Check if ALL keywords appear in the text (AND logic)
        if all(term in text_lower for term in keyword_terms):
            # Calculate relevance score based on keyword frequency
            score = sum(text_lower.count(term) for term in keyword_terms)
            # Normalize by text length to avoid bias toward longer texts
            score = score / max(len(text_content.split()), 1)

            # Create match object in same format as query results
            match = {
                "id": vector.get("id", ""),
                "score": score,
                "metadata": metadata
            }

            matched_results.append(match)

    logger.info(f"[Keyword Search] Found {len(matched_results)} keyword matches")

    # Sort by relevance score (descending)
    matched_results.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Limit to top_k results
    matched_results = matched_results[:top_k]

    logger.info(f"[Keyword Search] Returning {len(matched_results)} results")
    if matched_results:
        logger.info(f"[Keyword Search] Sample result: id={matched_results[0].get('id')[:50]}, score={matched_results[0].get('score')}, has_metadata={bool(matched_results[0].get('metadata'))}")

    # Return in a format similar to query_vectors (which is JSON-serializable)
    return {"matches": matched_results}
