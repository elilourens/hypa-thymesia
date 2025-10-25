# routes/delete.py (or wherever your delete endpoint lives)

from typing import Tuple
from fastapi import APIRouter, Depends, HTTPException, Query
from core.deps import get_supabase
from core.security import get_current_user, AuthUser
from data_upload.pinecone_services import delete_vectors_by_ids

router = APIRouter(prefix="/ingest", tags=["ingestion"])

@router.delete("/delete-document")
async def delete_document(
    doc_id: str = Query(..., description="The UUID of the document to delete"),
    auth: AuthUser = Depends(get_current_user),
    supabase = Depends(get_supabase),
):
    """
    Delete a document and all associated data:
    - Text chunks and embeddings
    - Uploaded images and embeddings
    - Extracted deep embed images and embeddings
    - Storage files from all buckets
    - Database records (cascades automatically)
    """
    user_id = auth.id
    
    # Get all chunks and their vector registrations
    q = (supabase
        .table("app_vector_registry")
        .select("vector_id,app_chunks!inner(bucket,storage_path,modality)")
        .eq("app_chunks.doc_id", doc_id)
        .eq("app_chunks.user_id", user_id)
    ).execute()

    rows = q.data or []
    if not rows:
        raise HTTPException(404, detail="No vectors found for this document")

    # Separate vector IDs by modality and index
    text_ids = []
    image_ids = []
    extracted_image_ids = []
    files: set[Tuple[str, str]] = set()
    
    for r in rows:
        ch = r["app_chunks"]
        bucket = ch.get("bucket")
        path = ch.get("storage_path")
        files.add((bucket, path))
        
        modality = ch.get("modality")
        if modality == "text":
            text_ids.append(r["vector_id"])
        elif modality == "image":
            # Distinguish extracted images from uploaded images by bucket
            if bucket == "extracted-images":
                extracted_image_ids.append(r["vector_id"])
            else:
                image_ids.append(r["vector_id"])

    # Delete from Pinecone (3 separate indexes)
    if text_ids:
        delete_vectors_by_ids(
            ids=text_ids,
            modality="text",
            namespace=user_id
        )
    
    if image_ids:
        delete_vectors_by_ids(
            ids=image_ids,
            modality="image",
            namespace=user_id
        )
    
    if extracted_image_ids:
        delete_vectors_by_ids(
            ids=extracted_image_ids,
            modality="extracted_image",
            namespace=user_id
        )

    # Delete files from Supabase storage (all buckets)
    for bucket, path in files:
        try:
            supabase.storage.from_(bucket).remove([path])
        except Exception as e:
            print(f"Storage delete failed for {bucket}/{path}: {e}")

    # Delete from database (cascades to app_chunks and app_vector_registry)
    supabase.table("app_doc_meta").delete().eq(
        "doc_id", doc_id
    ).eq("user_id", user_id).execute()

    return {
        "doc_id": doc_id,
        "status": "deleted",
        "deleted_vectors": len(text_ids) + len(image_ids) + len(extracted_image_ids),
        "deleted_files": len(files),
        "breakdown": {
            "text_chunks": len(text_ids),
            "uploaded_images": len(image_ids),
            "extracted_images": len(extracted_image_ids),
        }
    }