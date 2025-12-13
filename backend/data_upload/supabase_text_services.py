import os
from typing import Optional, List, Dict, Any
from uuid import uuid4
from datetime import datetime

from supabase import Client

from data_upload.pinecone_services import build_vector_item, upsert_vectors
from utils.db_helpers import ensure_doc_meta, register_vectors, sha256_hash

TEXT_BUCKET = os.getenv("TEXT_BUCKET", "texts")


def upload_text_to_bucket(
    supabase: Client,
    file_content: bytes,
    filename: str,
    bucket: str = TEXT_BUCKET,
    mime_type: Optional[str] = None,
) -> Optional[str]:
    """
    Upload a text/PDF/docx file to Supabase with correct MIME type.
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".txt", ".md", ".rtf", ".pdf", ".docx", ".ppt", ".pptx"]:
        return None

    file_path = f"uploads/{uuid4()}_{filename}"
    resp = supabase.storage.from_(bucket).upload(
        file_path,
        file_content,
        {"content-type": mime_type or "application/octet-stream"},
    )
    return file_path if resp else None


def delete_text_from_bucket(supabase: Client, filepath: str, bucket: str = TEXT_BUCKET) -> bool:
    try:
        res = supabase.storage.from_(bucket).remove([filepath])
        return any(obj.get("name") == filepath for obj in (res or []))
    except Exception as e:
        print(f"Deletion failed: {e}")
        return False


def wipe_text_from_bucket(supabase: Client, bucket: str = TEXT_BUCKET) -> str:
    return supabase.storage.empty_bucket(bucket)


def _insert_chunk_rows(
    supabase: Client,
    *,
    user_id: str,
    doc_id: str,
    storage_path: str,
    bucket: str,
    mime_type: str,
    text_chunks: List[str],
    size_bytes: int | None = None,
) -> List[Dict[str, Any]]:
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
            "user_id": user_id,
            **({"size_bytes": int(size_bytes)} if (idx == 1 and size_bytes is not None) else {}),
        })
    data = supabase.table("app_chunks").insert(rows).execute()
    return data.data or []


def ingest_text_chunks(
    supabase: Client,
    *,
    user_id: str,
    filename: str,
    storage_path: str,
    text_chunks: List[str],
    mime_type: str,
    embedding_model: str,
    embedding_dim: int,
    embed_text_vectors: List[List[float]],
    namespace: Optional[str] = None,
    doc_id: Optional[str] = None,
    embedding_version: int = 1,
    extra_vector_metadata: Optional[List[Dict[str, Any]]] = None,
    size_bytes: int | None = None,
    group_id: Optional[str] = None,
) -> Dict[str, Any]:
    if len(text_chunks) != len(embed_text_vectors):
        raise ValueError("Number of text chunks must equal number of embeddings")

    if extra_vector_metadata is not None and len(extra_vector_metadata) != len(text_chunks):
        raise ValueError("extra_vector_metadata length must match number of text chunks")

    if embedding_dim and embedding_dim != 384:
        raise ValueError(f"Embedding dim mismatch for text: got {embedding_dim}, expected 384.")

    doc_id = doc_id or str(uuid4())

    # ensure meta row (stores group_id)
    ensure_doc_meta(supabase, user_id=user_id, doc_id=doc_id, group_id=group_id)

    chunk_rows = _insert_chunk_rows(
        supabase,
        user_id=user_id,
        doc_id=doc_id,
        storage_path=storage_path,
        bucket=TEXT_BUCKET,
        mime_type=mime_type,
        text_chunks=text_chunks,
        size_bytes=size_bytes,
    )

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
            "content_sha256": sha256_hash(text),
            "title": filename,
            "text": text,
            "upload_date": datetime.utcnow().date().isoformat(),
        }

        if group_id:
            metadata["group_id"] = group_id

        if extra_vector_metadata is not None:
            extra = extra_vector_metadata[idx] or {}
            if isinstance(extra.get("page_number"), int):
                metadata["page_number"] = extra["page_number"]
            for k, v in extra.items():
                if k == "page_number":
                    continue
                if v is not None:
                    metadata[k] = v

        metadata = {k: v for k, v in metadata.items() if v is not None}

        vectors.append(build_vector_item(vector_id=vector_id, values=emb, metadata=metadata))
        registry.append({
            "vector_id": vector_id,
            "chunk_id": ch["chunk_id"],
            "embedding_model": embedding_model,
            "embedding_version": embedding_version,
        })

    upsert_vectors(vectors=vectors, modality="text", namespace=namespace or str(user_id))
    register_vectors(supabase, registry)

    return {
        "doc_id": doc_id,
        "vector_count": len(vectors),
        "namespace": (namespace or str(user_id)),
    }
