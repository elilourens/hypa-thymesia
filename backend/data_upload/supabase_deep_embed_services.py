# data_upload/supabase_deep_embed_services.py

import os
import logging
from typing import List, Dict, Any, Optional
from uuid import uuid4
from datetime import datetime
from supabase import Client

from data_upload.pinecone_services import build_vector_item, upsert_vectors
from utils.db_helpers import ensure_doc_meta, register_vectors

logger = logging.getLogger(__name__)

EXTRACTED_IMAGES_BUCKET = os.getenv("EXTRACTED_IMAGES_BUCKET", "extracted-images")


def upload_extracted_image_to_bucket(
    supabase: Client,
    image_bytes: bytes,
    user_id: str,
    doc_id: str,
    page_number: Optional[int],
    image_index: int,
    format: str = "png",
) -> Dict[str, str]:
    """Upload extracted image to Supabase storage."""
    page_str = f"page_{page_number}" if page_number else "img"
    filename = f"{page_str}_img_{image_index}.{format}"
    storage_path = f"{user_id}/{doc_id}/{filename}"
    
    try:
        supabase.storage.from_(EXTRACTED_IMAGES_BUCKET).upload(
            path=storage_path,
            file=image_bytes,
            file_options={"content-type": f"image/{format}"}
        )
    except Exception as e:
        try:
            supabase.storage.from_(EXTRACTED_IMAGES_BUCKET).update(
                path=storage_path,
                file=image_bytes,
                file_options={"content-type": f"image/{format}"}
            )
        except Exception as update_error:
            raise RuntimeError(f"Failed to upload image: {e}, update failed: {update_error}")
    
    public_url = supabase.storage.from_(EXTRACTED_IMAGES_BUCKET).get_public_url(storage_path)
    
    return {
        "storage_path": storage_path,
        "public_url": public_url,
        "bucket": EXTRACTED_IMAGES_BUCKET,
    }




def ingest_deep_embed_images(
    supabase: Client,
    *,
    user_id: str,
    doc_id: str,
    parent_filename: str,
    parent_storage_path: str,
    images_data: List[Dict[str, Any]],
    embed_image_vectors: List[List[float]],
    embedding_model: str = "clip-ViT-B-32",
    embedding_dim: int = 512,
    namespace: Optional[str] = None,
    embedding_version: int = 1,
    group_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ingest extracted images to:
    1. Supabase storage (extracted-images bucket)
    2. Supabase database (app_chunks, app_vector_registry)
    3. Pinecone (extracted-images index)
    """
    if len(images_data) != len(embed_image_vectors):
        raise ValueError("Number of images must equal number of embeddings")
    
    if embedding_dim != 512:
        raise ValueError(f"CLIP embedding dim must be 512, got {embedding_dim}")
    
    if not images_data:
        return {
            "doc_id": doc_id,
            "images_ingested": 0,
            "namespace": namespace or user_id,
        }

    ensure_doc_meta(supabase, user_id=user_id, doc_id=doc_id, group_id=group_id)
    
    # Find the max chunk_index for this doc to continue numbering
    existing_chunks = supabase.table("app_chunks").select("chunk_index").eq(
        "doc_id", doc_id
    ).order("chunk_index", desc=True).limit(1).execute()
    
    max_chunk_index = 0
    if existing_chunks.data and len(existing_chunks.data) > 0:
        max_chunk_index = existing_chunks.data[0]["chunk_index"]
    
    logger.info(f"Starting image chunk_index at {max_chunk_index + 1} (max existing: {max_chunk_index})")
    
    chunk_rows = []
    vectors = []
    registry = []
    
    for idx, (img_data, emb) in enumerate(zip(images_data, embed_image_vectors)):
        # Upload to Supabase storage
        upload_result = upload_extracted_image_to_bucket(
            supabase=supabase,
            image_bytes=img_data["image_bytes"],
            user_id=user_id,
            doc_id=doc_id,
            page_number=img_data.get("page_number"),
            image_index=img_data["image_index"],
            format=img_data.get("format", "png"),
        )
        
        # Create chunk row with CONTINUING chunk_index
        chunk_id = str(uuid4())
        chunk_index = max_chunk_index + idx + 1
        
        chunk_rows.append({
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "chunk_index": chunk_index,
            "modality": "image",
            "storage_path": upload_result["storage_path"],
            "bucket": upload_result["bucket"],
            "mime_type": f"image/{img_data.get('format', 'png')}",
            "user_id": user_id,
        })
        
        # Build Pinecone metadata
        vector_id = f"{chunk_id}:{embedding_version}"
        metadata = {
            "user_id": user_id,
            "doc_id": doc_id,
            "chunk_id": chunk_id,
            "chunk_index": chunk_index,
            "modality": "image",
            "source": "extracted",
            "bucket": upload_result["bucket"],
            "storage_path": upload_result["storage_path"],
            "public_url": upload_result["public_url"],
            "mime_type": f"image/{img_data.get('format', 'png')}",
            "embedding_model": embedding_model,
            "embedding_version": embedding_version,
            "parent_filename": parent_filename,
            "parent_storage_path": parent_storage_path,
            "dimensions": f"{img_data['width']}x{img_data['height']}",
            "upload_date": datetime.utcnow().date().isoformat(),
        }
        
        if img_data.get("page_number") is not None:
            metadata["page_number"] = img_data["page_number"]
        if img_data.get("image_index") is not None:
            metadata["image_index"] = img_data["image_index"]
        if group_id:
            metadata["group_id"] = group_id
        
        metadata = {k: v for k, v in metadata.items() if v is not None}
        
        vectors.append(build_vector_item(
            vector_id=vector_id,
            values=emb,
            metadata=metadata
        ))
        
        registry.append({
            "vector_id": vector_id,
            "chunk_id": chunk_id,
            "embedding_model": embedding_model,
            "embedding_version": embedding_version,
        })
    
    # Insert into Supabase
    if chunk_rows:
        supabase.table("app_chunks").insert(chunk_rows).execute()

    if registry:
        register_vectors(supabase, registry)
    
    # Upsert to Pinecone EXTRACTED IMAGES index
    if vectors:
        upsert_vectors(
            vectors=vectors,
            modality="extracted_image",
            namespace=namespace or user_id
        )
    
    return {
        "doc_id": doc_id,
        "images_ingested": len(vectors),
        "namespace": namespace or user_id,
    }