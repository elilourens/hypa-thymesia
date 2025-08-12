# data_upload/pinecone_services.py
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv
from pinecone import Pinecone  # pinecone>=5

load_dotenv()

_PINECONE_KEY = os.getenv("PINECONE_API_KEY") or os.getenv("PINECONE_KEY")
if not _PINECONE_KEY:
    raise RuntimeError("Missing PINECONE_API_KEY (or PINECONE_KEY).")

pc = Pinecone(
    api_key=_PINECONE_KEY,
    environment=os.getenv("PINECONE_ENVIRONMENT") or None,
)

INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
if not INDEX_NAME:
    raise RuntimeError("Missing PINECONE_INDEX_NAME.")
index = pc.Index(INDEX_NAME)

MAX_BATCH = int(os.getenv("PINECONE_MAX_BATCH", "100"))

def _chunked(xs: list, n: int):
    for i in range(0, len(xs), n):
        yield xs[i:i+n]

def build_vector_item(*, vector_id: str, values: List[float], metadata: Dict[str, Any]) -> Dict[str, Any]:
    md = dict(metadata)
    md.setdefault("server_upserted_at", datetime.utcnow().isoformat() + "Z")
    return {"id": vector_id, "values": values, "metadata": md}

def upsert_vectors(vectors: List[Dict[str, Any]], namespace: Optional[str] = None) -> None:
    if not vectors:
        return
    bsz = max(1, min(MAX_BATCH, len(vectors)))
    for batch in _chunked(vectors, bsz):
        index.upsert(vectors=batch, namespace=namespace)

def delete_vectors_by_ids(ids: List[str], namespace: Optional[str] = None) -> None:
    if ids:
        index.delete(ids=ids, namespace=namespace)
