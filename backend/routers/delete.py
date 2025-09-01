from typing import List, Tuple
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
    user_id = auth.id
    q = (supabase
        .table("app_vector_registry")
        .select("vector_id,app_chunks!inner(bucket,storage_path,modality)")
        .eq("app_chunks.doc_id", doc_id)
        .eq("app_chunks.user_id", user_id)
    ).execute()

    rows = q.data or []
    if not rows:
        raise HTTPException(404, detail="No vectors found for this document")

    text_ids, image_ids = [], []
    files: set[Tuple[str, str]] = set()
    for r in rows:
        ch = r["app_chunks"]
        files.add((ch["bucket"], ch["storage_path"]))
        if ch.get("modality") == "text":
            text_ids.append(r["vector_id"])
        elif ch.get("modality") == "image":
            image_ids.append(r["vector_id"])

    if text_ids:
        delete_vectors_by_ids(ids=text_ids, modality="text", namespace=user_id)
    if image_ids:
        delete_vectors_by_ids(ids=image_ids, modality="image", namespace=user_id)

    for bucket, path in files:
        try:
            supabase.storage.from_(bucket).remove([path])
        except Exception as e:
            print(f"Storage delete failed for {bucket}/{path}: {e}")

    supabase.table("app_doc_meta").delete().eq("doc_id", doc_id).eq("user_id", user_id).execute()

    return {"deleted_vectors": len(text_ids) + len(image_ids), "deleted_files": len(files), "doc_id": doc_id, "status": "deleted"}
