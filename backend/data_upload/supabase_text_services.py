# data_upload/supabase_text_services.py
import os
import hashlib
from typing import Optional, List, Dict, Any
from uuid import uuid4
from datetime import datetime

from dotenv import load_dotenv
from supabase import create_client, Client

from data_upload.pinecone_services import build_vector_item, upsert_vectors

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
TEXT_BUCKET = os.getenv("TEXT_BUCKET", "texts")


def upload_text_to_bucket(file_content: bytes, filename: str, bucket: str = TEXT_BUCKET) -> Optional[str]:
    # allow common text/doc types; reject others early
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".txt", ".md", ".rtf", ".pdf", ".docx"]:
        return None
    file_path = f"uploads/{uuid4()}_{filename}"
    # Supabase Python storage returns a dict or raises; treat non-exception as success
    resp = supabase.storage.from_(bucket).upload(file_path, file_content)
    # Some SDK versions return {'Key': 'path'} — treat truthy as success
    return file_path if resp else None


def delete_text_from_bucket(filepath: str, bucket: str = TEXT_BUCKET) -> bool:
    try:
        res = supabase.storage.from_(bucket).remove([filepath])
        return any(obj.get("name") == filepath for obj in (res or []))
    except Exception as e:
        print(f"Deletion failed: {e}")
        return False


def wipe_text_from_bucket(bucket: str = TEXT_BUCKET) -> str:
    return supabase.storage.empty_bucket(bucket)


def _sha256_text(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def _insert_chunk_rows(
    *,
    user_id: str,                   # <-- NEW: required so we write ownership
    doc_id: str,
    storage_path: str,
    bucket: str,
    mime_type: str,
    text_chunks: List[str],
) -> List[Dict[str, Any]]:
    """
    Inserts one row per text chunk into app_chunks, including user_id.
    Returns the inserted rows (with chunk_id, etc.).
    """
    rows: List[Dict[str, Any]] = []
    for idx, _ in enumerate(text_chunks, start=1):
        rows.append({
            "chunk_id": str(uuid4()),
            "doc_id": doc_id,
            "chunk_index": idx,
            "modality": "text",
            "storage_path": storage_path,
            "bucket": bucket,
            "mime_type": mime_type,
            "user_id": user_id,     # <-- CRITICAL: enforce ownership at write time
        })
    data = supabase.table("app_chunks").insert(rows).execute()
    return data.data or []


def _register_vectors(rows: List[Dict[str, Any]]) -> None:
    if rows:
        supabase.table("app_vector_registry").upsert(rows).execute()


def ingest_text_chunks(
    *,
    user_id: str,                             # <-- passed from router, used here
    filename: str,
    storage_path: str,
    text_chunks: List[str],
    mime_type: str,
    embedding_model: str,
    embedding_dim: int,
    embed_text_vectors: List[List[float]],   # already computed embeddings
    namespace: Optional[str] = None,
    doc_id: Optional[str] = None,
    embedding_version: int = 1,
    # Optional per-chunk metadata merged into Pinecone vector metadata
    # e.g. [{"page_number": 1, "char_start": 0, "char_end": 512, "preview": "..."}]
    extra_vector_metadata: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    # Basic validations
    if len(text_chunks) != len(embed_text_vectors):
        raise ValueError("Number of text chunks must equal number of embeddings")

    if extra_vector_metadata is not None and len(extra_vector_metadata) != len(text_chunks):
        raise ValueError("extra_vector_metadata length must match number of text chunks")

    doc_id = doc_id or str(uuid4())

    # 1) create app_chunks rows (WITH user_id)
    chunk_rows = _insert_chunk_rows(
        user_id=user_id,                    # <-- pass through
        doc_id=doc_id,
        storage_path=storage_path,
        bucket=TEXT_BUCKET,
        mime_type=mime_type,
        text_chunks=text_chunks,
    )

    # 2) build Pinecone vectors + registry rows
    vectors: List[Dict[str, Any]] = []
    registry: List[Dict[str, Any]] = []

    for idx, (emb, ch, text) in enumerate(zip(embed_text_vectors, chunk_rows, text_chunks)):
        vector_id = f"{ch['chunk_id']}:{embedding_version}"

        metadata: Dict[str, Any] = {
            "user_id": user_id,
            "doc_id": ch["doc_id"],
            "chunk_id": ch["chunk_id"],
            "chunk_index": ch["chunk_index"],
            "modality": "text",
            "bucket": ch["bucket"],
            "storage_path": ch["storage_path"],
            "mime_type": ch["mime_type"],
            "embedding_model": embedding_model,
            "embedding_version": embedding_version,
            "content_sha256": _sha256_text(text),
            "title": filename,
            "upload_date": datetime.utcnow().date().isoformat(),
        }

        # Merge any caller-provided per-chunk metadata (page_number, offsets, preview, etc.)
        if extra_vector_metadata is not None:
            extra = extra_vector_metadata[idx] or {}
            metadata.update(extra)

        vectors.append(build_vector_item(vector_id=vector_id, values=emb, metadata=metadata))
        registry.append({
            "vector_id": vector_id,
            "chunk_id": ch["chunk_id"],
            "embedding_model": embedding_model,
            "embedding_version": embedding_version,
        })

    # 3) upsert vectors to Pinecone under tenant namespace (user_id)
    upsert_vectors(vectors, namespace=namespace or str(user_id))

    # 4) register vectors in DB
    _register_vectors(registry)

    return {
        "doc_id": doc_id,
        "vector_count": len(vectors),
        "namespace": (namespace or str(user_id)),
    }
