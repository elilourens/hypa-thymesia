import os
import hashlib
from typing import Optional, List, Dict, Any
from uuid import uuid4
from datetime import datetime
from io import BytesIO

from dotenv import load_dotenv
from supabase import create_client, Client
from PIL import Image

from data_upload.pinecone_services import build_vector_item, upsert_vectors

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
IMAGE_BUCKET = os.getenv("IMAGE_BUCKET", "images")


def upload_image_to_bucket(file_content: bytes, filename: str, bucket: str = IMAGE_BUCKET) -> Optional[str]:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        return None
    try:
        img = Image.open(BytesIO(file_content))
        img.verify()
    except Exception:
        return None
    file_path = f"uploads/{uuid4()}_{filename}"
    resp = supabase.storage.from_(bucket).upload(file_path, file_content)
    return file_path if resp else None


def delete_image_from_bucket(filepath: str, bucket: str = IMAGE_BUCKET) -> bool:
    try:
        res = supabase.storage.from_(bucket).remove([filepath])
        return any(obj.get("name") == filepath for obj in (res or []))
    except Exception as e:
        print(f"Deletion failed: {e}")
        return False


def wipe_images_from_bucket(bucket: str = IMAGE_BUCKET) -> str:
    return supabase.storage.empty_bucket(bucket)


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _ensure_doc_meta(*, user_id: str, doc_id: str, group_id: Optional[str]) -> None:
    supabase.table("app_doc_meta").upsert(
        {"doc_id": doc_id, "user_id": user_id, "group_id": group_id},
        on_conflict="doc_id",
    ).execute()


def _insert_single_image_chunk(
    *,
    user_id: str,
    doc_id: str,
    storage_path: str,
    bucket: str,
    mime_type: str,
    size_bytes: int | None = None,
) -> Dict[str, Any]:
    row = {
        "chunk_id": str(uuid4()),
        "doc_id": doc_id,
        "chunk_index": 1,
        "modality": "image",
        "storage_path": storage_path,
        "bucket": bucket,
        "mime_type": mime_type,
        "user_id": user_id,
        "size_bytes": int(size_bytes) if size_bytes is not None else None,
    }
    data = supabase.table("app_chunks").insert(row).execute()
    if not data.data:
        raise RuntimeError("Insert into app_chunks returned no rows")
    return data.data[0]


def _register_vectors(rows: List[Dict[str, Any]]) -> None:
    if rows:
        supabase.table("app_vector_registry").upsert(rows).execute()


def ingest_single_image(
    *,
    user_id: str,
    filename: str,
    storage_path: str,
    file_bytes: bytes,
    mime_type: str,
    embedding_model: str,
    embedding_dim: int,
    embed_image_vectors: List[List[float]],  # length==1
    namespace: Optional[str] = None,
    doc_id: Optional[str] = None,
    embedding_version: int = 1,
    size_bytes: int | None = None,
    group_id: Optional[str] = None,  # NEW
) -> Dict[str, Any]:
    if len(embed_image_vectors) != 1:
        raise ValueError("Expected exactly one image embedding")
    if embedding_dim and embedding_dim != 512:
        raise ValueError(f"Embedding dim mismatch for image: got {embedding_dim}, expected 512.")

    doc_id = doc_id or str(uuid4())
    _ensure_doc_meta(user_id=user_id, doc_id=doc_id, group_id=group_id)

    chunk_row = _insert_single_image_chunk(
        user_id=user_id,
        doc_id=doc_id,
        storage_path=storage_path,
        bucket=IMAGE_BUCKET,
        mime_type=mime_type,
        size_bytes=size_bytes,
    )

    emb = embed_image_vectors[0]
    vector_id = f"{chunk_row['chunk_id']}:{embedding_version}"
    metadata = {
        "user_id": user_id,
        "doc_id": chunk_row["doc_id"],
        "chunk_id": chunk_row["chunk_id"],
        "chunk_index": chunk_row["chunk_index"],
        "modality": "image",
        "bucket": chunk_row["bucket"],
        "storage_path": chunk_row["storage_path"],
        "mime_type": chunk_row["mime_type"],
        "embedding_model": embedding_model,
        "embedding_version": embedding_version,
        "content_sha256": _sha256_bytes(file_bytes),
        "title": filename,
        "upload_date": datetime.utcnow().date().isoformat(),
    }
    if group_id:
        metadata["group_id"] = group_id

    vector_item = build_vector_item(vector_id=vector_id, values=emb, metadata=metadata)
    upsert_vectors(vectors=[vector_item], modality="image", namespace=namespace or str(user_id))

    _register_vectors([{
        "vector_id": vector_id,
        "chunk_id": chunk_row["chunk_id"],
        "embedding_model": embedding_model,
        "embedding_version": embedding_version,
    }])

    return {
        "doc_id": doc_id,
        "vector_count": 1,
        "namespace": (namespace or str(user_id)),
    }
