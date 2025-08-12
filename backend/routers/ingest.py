# app/routers/ingest.py
import os
from uuid import uuid4
from tempfile import NamedTemporaryFile
from typing import List, Any, Dict
from datetime import datetime

from dotenv import load_dotenv
from fastapi import APIRouter, File, UploadFile, HTTPException, Query

from data_upload.supabase_text_services import (
    upload_text_to_bucket,
    ingest_text_chunks,
)
from data_upload.supabase_image_services import (
    upload_image_to_bucket,
    ingest_single_image,
)
from data_upload.pinecone_services import delete_vectors_by_ids
from supabase import create_client, Client

# metadata-extracting chunkers
from ingestion.text.extract_text_from_docx import extract_docx_text_metadata
from ingestion.text.extract_text_from_pdf import extract_pdf_text_metadata
from ingestion.text.extract_text_from_txt import extract_txt_text_metadata

# embedding functions
from embed.embeddings import embed_texts, embed_images

router = APIRouter(prefix="/ingest", tags=["ingestion"])
load_dotenv()

# Supabase client (needed for deletion)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Shared model/dim for both text+image
EMBED_MODEL = os.getenv("EMBED_MODEL", "clip-ViT-B-32")
EMBED_DIM   = int(os.getenv("EMBED_DIM", "512"))


@router.post("/upload-text-and-images")
async def ingest_text_and_image_files(file: UploadFile = File(...)):
    user_id = "dev_user"  # TODO: replace with real auth user id

    content = await file.read()
    ext = file.filename.rsplit(".", 1)[-1].lower()
    suffix = f".{ext}"

    supported_text = ("docx", "pdf", "txt", "md")
    supported_images = ("png", "jpeg", "jpg", "webp")

    if ext not in supported_text + supported_images:
        raise HTTPException(400, detail=f"Unsupported file type: {ext}")

    if ext in supported_images:
        storage_path = upload_image_to_bucket(content, file.filename)
        if not storage_path:
            raise HTTPException(500, detail="Failed to upload image to storage")

        image_vectors = await embed_images([content])
        result = ingest_single_image(
            user_id=user_id,
            filename=file.filename,
            storage_path=storage_path,
            file_bytes=content,
            mime_type=file.content_type or "image/jpeg",
            embedding_model=EMBED_MODEL,
            embedding_dim=EMBED_DIM,
            embed_image_vectors=image_vectors,
            namespace=user_id,
            doc_id=str(uuid4()),
            embedding_version=1,
        )

        return {"doc_id": result["doc_id"], "chunks_ingested": result["vector_count"]}

    # TEXT
    storage_path = upload_text_to_bucket(content, file.filename)
    if not storage_path:
        raise HTTPException(500, detail="Failed to upload text to storage")

    with NamedTemporaryFile(prefix="upload_", suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if ext == "docx":
            meta_out = extract_docx_text_metadata(tmp_path, user_id)
        elif ext == "pdf":
            meta_out = extract_pdf_text_metadata(tmp_path, user_id)
        elif ext in ("txt", "md"):
            meta_out = extract_txt_text_metadata(tmp_path, user_id)
        else:
            meta_out = {"text_chunks": []}
        chunks: List[Dict[str, Any]] = meta_out.get("text_chunks", [])
    finally:
        os.unlink(tmp_path)

    if not chunks:
        raise HTTPException(422, detail="No text chunks were extracted")

    texts = [c["chunk_text"] for c in chunks]
    text_vectors = await embed_texts(texts)

    result = ingest_text_chunks(
        user_id=user_id,
        filename=file.filename,
        storage_path=storage_path,
        text_chunks=texts,
        mime_type=file.content_type or "text/plain",
        embedding_model=EMBED_MODEL,
        embedding_dim=EMBED_DIM,
        embed_text_vectors=text_vectors,
        namespace=user_id,
        doc_id=str(uuid4()),
        embedding_version=1,
    )

    return {"doc_id": result["doc_id"], "chunks_ingested": result["vector_count"]}


@router.delete("/delete-document")
async def delete_document(
    doc_id: str = Query(..., description="The UUID of the document to delete"),
    user_id: str = Query(..., description="User/namespace ID"),
):
    """
    Deletes all vectors from Pinecone and the related files/chunks in Supabase for a given doc_id.
    """
    # 1) Fetch all vector IDs + file info for the doc
    q = (
        supabase.table("app_vector_registry")
        .select("vector_id,app_chunks!inner(bucket,storage_path)")
        .eq("app_chunks.doc_id", doc_id)
    ).execute()

    rows = q.data or []
    if not rows:
        raise HTTPException(404, detail="No vectors found for this document")

    vector_ids = [r["vector_id"] for r in rows]
    files = {(r["app_chunks"]["bucket"], r["app_chunks"]["storage_path"]) for r in rows}

    # 2) Delete from Pinecone
    delete_vectors_by_ids(vector_ids, namespace=user_id)

    # 3) Delete files from Supabase storage
    for bucket, path in files:
        try:
            supabase.storage.from_(bucket).remove([path])
        except Exception as e:
            print(f"Storage delete failed for {bucket}/{path}: {e}")

    # 4) Delete chunks (FK cascade removes registry entries)
    supabase.table("app_chunks").delete().eq("doc_id", doc_id).execute()

    return {
        "deleted_vectors": len(vector_ids),
        "deleted_files": len(files),
        "doc_id": doc_id,
        "status": "deleted",
    }
