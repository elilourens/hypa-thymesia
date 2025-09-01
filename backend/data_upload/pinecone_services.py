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

# NOTE: Pinecone >=5 does not require an environment/region param for serverless;
# keeping optional for compatibility if you set it.
pc = Pinecone(
    api_key=_PINECONE_KEY,
    environment=os.getenv("PINECONE_ENVIRONMENT") or None,
)

TEXT_INDEX_NAME = os.getenv("PINECONE_TEXT_INDEX_NAME")
IMAGE_INDEX_NAME = os.getenv("PINECONE_IMAGE_INDEX_NAME")

if not TEXT_INDEX_NAME:
    raise RuntimeError("Missing PINECONE_TEXT_INDEX_NAME.")
if not IMAGE_INDEX_NAME:
    raise RuntimeError("Missing PINECONE_IMAGE_INDEX_NAME.")

# Lazy init: create Index handles
_text_index = pc.Index(TEXT_INDEX_NAME)
_image_index = pc.Index(IMAGE_INDEX_NAME)

# Model dims (lock these in; change here if you ever swap models)
TEXT_DIM = 384          # all-MiniLM-L12-v2
IMAGE_TEXT_DIM = 512    # clip-ViT-B-32 (text+image)

MAX_BATCH = int(os.getenv("PINECONE_MAX_BATCH", "100"))

Modality = Literal["text", "image", "clip_text"]  # clip_text = CLIP text encoder

# -------------------- Utilities --------------------
def _chunked(xs: list, n: int):
    for i in range(0, len(xs), n):
        yield xs[i:i+n]

def _index_for_modality(modality: Modality):
    if modality == "text":
        return _text_index, TEXT_DIM
    # Both CLIP-image and CLIP-text embeddings live in the same 512-D space
    if modality in ("image", "clip_text"):
        return _image_index, IMAGE_TEXT_DIM
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
    *   ,
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
