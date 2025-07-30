# app/routers/ingest.py

import os
import uuid
from tempfile import NamedTemporaryFile
from typing import List, Dict, Any
from fastapi import APIRouter, File, UploadFile, Depends, HTTPException

from data_upload.supabase_text_upload import upload_text_to_bucket

# your metadata‑extracting chunkers
from ingestion.text.extract_text_from_docx import extract_docx_text_metadata
from ingestion.text.extract_text_from_pdf import extract_pdf_text_metadata
from ingestion.text.extract_text_from_txt import extract_txt_text_metadata

from embed.embeddings import embed_texts
from services.pinecone_service import upsert_chunks
from app.dependencies import get_current_user

router = APIRouter(prefix="/ingest", tags=["ingestion"])

@router.post("/text", summary="Upload & ingest a text/pdf/docx file")
async def ingest_text_file(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    # Read raw bytes
    content = await file.read()
    ext = file.filename.rsplit(".", 1)[-1].lower()

    # 1) persist to Supabase
    supa_path = upload_text_to_bucket(content, file.filename)
    if not supa_path:
        raise HTTPException(500, detail="Failed to upload to storage")

    # 2) write to temp file so extractors can read from disk
    suffix = f".{ext}"
    with NamedTemporaryFile(prefix="upload_", suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # 3) dispatch to the right metadata extractor
        if ext == "docx":
            meta_out = extract_docx_text_metadata(tmp_path, user_id)
        elif ext == "pdf":
            meta_out = extract_pdf_text_metadata(tmp_path, user_id)
        elif ext in ("txt", "md"):
            meta_out = extract_txt_text_metadata(tmp_path, user_id)
        else:
            raise HTTPException(400, detail=f"Unsupported file type: {ext}")

        chunks: List[Dict[str, Any]] = meta_out.get("text_chunks", [])
    finally:
        os.unlink(tmp_path)

    if not chunks:
        raise HTTPException(422, detail="No text chunks were extracted")

    # 4) embed + upsert
    texts = [c["chunk_text"] for c in chunks]
    embeddings = await embed_texts(texts)

    items = []
    for idx, (emb, meta) in enumerate(zip(embeddings, chunks)):
        # generate a stable, unique chunk id
        chunk_id = f"{user_id}::{file.filename}::{idx}"
        meta["storage_path"] = supa_path
        items.append({
            "id": chunk_id,
            "values": emb,
            "metadata": meta,
        })

    success = await upsert_chunks(items)
    if not success:
        raise HTTPException(500, detail="Failed to upsert embeddings")

    return {
        "chunks_ingested": len(items),
        "storage_path": supa_path,
    }
