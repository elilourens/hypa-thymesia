import os
import logging
from typing import Optional, List, Dict, Any
from uuid import uuid4
from datetime import datetime
from io import BytesIO

from supabase import Client
from PIL import Image

from data_upload.pinecone_services import build_vector_item, upsert_vectors
from utils.db_helpers import ensure_doc_meta, register_vectors, sha256_hash

logger = logging.getLogger(__name__)

IMAGE_BUCKET = os.getenv("IMAGE_BUCKET", "images")


def upload_image_to_bucket(supabase: Client, file_content: bytes, filename: str, bucket: str = IMAGE_BUCKET) -> Optional[str]:
    logger.info(f"upload_image_to_bucket called: filename={filename}, size={len(file_content)} bytes, bucket={bucket}")

    ext = os.path.splitext(filename)[1].lower()
    logger.info(f"File extension: {ext}")

    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        logger.warning(f"Unsupported image extension: {ext}")
        return None

    try:
        logger.info("Opening image with PIL...")
        img = Image.open(BytesIO(file_content))
        logger.info(f"Image opened successfully: format={img.format}, size={img.size}")

        logger.info("Verifying image...")
        img.verify()
        logger.info("Image verification passed")
    except Exception as e:
        logger.error(f"Image validation failed: {e}", exc_info=True)
        return None

    file_path = f"uploads/{uuid4()}_{filename}"
    logger.info(f"Uploading to bucket '{bucket}' at path: {file_path}")

    try:
        resp = supabase.storage.from_(bucket).upload(file_path, file_content)
        logger.info(f"Upload response: {resp}")

        if resp:
            logger.info(f"Upload successful, returning path: {file_path}")
            return file_path
        else:
            logger.error("Upload returned empty response")
            return None
    except Exception as e:
        logger.error(f"Upload failed: {e}", exc_info=True)
        return None


def delete_image_from_bucket(supabase: Client, filepath: str, bucket: str = IMAGE_BUCKET) -> bool:
    try:
        res = supabase.storage.from_(bucket).remove([filepath])
        return any(obj.get("name") == filepath for obj in (res or []))
    except Exception as e:
        print(f"Deletion failed: {e}")
        return False


def wipe_images_from_bucket(supabase: Client, bucket: str = IMAGE_BUCKET) -> str:
    return supabase.storage.empty_bucket(bucket)


def _insert_single_image_chunk(
    supabase: Client,
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


def ingest_single_image(
    supabase: Client,
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
    group_id: Optional[str] = None,
    bucket: str = "images",  # Allow custom bucket
) -> Dict[str, Any]:
    if len(embed_image_vectors) != 1:
        raise ValueError("Expected exactly one image embedding")
    if embedding_dim and embedding_dim != 512:
        raise ValueError(f"Embedding dim mismatch for image: got {embedding_dim}, expected 512.")

    doc_id = doc_id or str(uuid4())
    ensure_doc_meta(supabase, user_id=user_id, doc_id=doc_id, group_id=group_id)

    chunk_row = _insert_single_image_chunk(
        supabase,
        user_id=user_id,
        doc_id=doc_id,
        storage_path=storage_path,
        bucket=bucket,
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
        "content_sha256": sha256_hash(file_bytes),
        "title": filename,
        "upload_date": datetime.utcnow().date().isoformat(),
    }
    if group_id:
        metadata["group_id"] = group_id

    vector_item = build_vector_item(vector_id=vector_id, values=emb, metadata=metadata)
    upsert_vectors(vectors=[vector_item], modality="image", namespace=namespace or str(user_id))

    register_vectors(supabase, [{
        "vector_id": vector_id,
        "chunk_id": chunk_row["chunk_id"],
        "embedding_model": embedding_model,
        "embedding_version": embedding_version,
    }])

    return {
        "doc_id": doc_id,
        "chunk_id": chunk_row["chunk_id"],
        "storage_path": chunk_row["storage_path"],
        "bucket": chunk_row["bucket"],
        "vector_count": 1,
        "namespace": (namespace or str(user_id)),
    }