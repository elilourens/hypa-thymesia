# app/routers/ingest.py

import os
from tempfile import NamedTemporaryFile
from typing import List, Any, Dict
from datetime import datetime
from dotenv import load_dotenv
from fastapi import APIRouter, File, UploadFile, HTTPException

from data_upload.supabase_text_services import upload_text_to_bucket
from data_upload.supabase_image_services import upload_image_to_bucket

# metadata-extracting chunkers
from ingestion.text.extract_text_from_docx import extract_docx_text_metadata
from ingestion.text.extract_text_from_pdf import extract_pdf_text_metadata
from ingestion.text.extract_text_from_txt import extract_txt_text_metadata

from embed.embeddings import embed_texts, embed_images
from data_upload.pinecone_services import upload_to_pinecone

router = APIRouter(prefix="/ingest", tags=["ingestion"])


load_dotenv()


@router.post("/upload-text-and-images", summary="Upload & ingest a text/pdf/docx/png/jpeg file")
async def ingest_text_and_image_files(
    file: UploadFile = File(...),
):
    # temppppp
    user_id = "dev_user"

    
    content = await file.read()
    ext = file.filename.rsplit(".", 1)[-1].lower()
    suffix = f".{ext}"

    supported_text = ("docx", "pdf", "txt", "md")
    supported_images = ("png", "jpeg", "jpg")

    if ext not in supported_text + supported_images:
        raise HTTPException(400, detail=f"Unsupported file type: {ext}")
    


    if ext in supported_images:
        supa_path = upload_image_to_bucket(content, file.filename)
    else:
        supa_path = upload_text_to_bucket(content, file.filename)
    
    
    
    if not supa_path:
        raise HTTPException(500, detail="Failed to upload to storage")

    
    
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

    if ext in supported_text and not chunks:
        raise HTTPException(422, detail="No text chunks were extracted")

    
    texts = [c["chunk_text"] for c in chunks]
    if ext in supported_images:
        embeddings = await embed_images([content])
    else:
        embeddings = await embed_texts(texts)

    # 5) upsert via Pinecone helper
    #    record_id can be the filename without extension,
    #    upload_date is ISO8601 UTC now
    record_id   = os.path.splitext(file.filename)[0]
    upload_date = datetime.utcnow().isoformat()

    success = upload_to_pinecone(
        file_type=ext,
        user_id=user_id,
        record_id=record_id,
        vectors=embeddings,
        upload_date=upload_date,
    )
    print(record_id)
    if not success:
        raise HTTPException(500, detail="Failed to upsert embeddings into Pinecone")

    return {
        "chunks_ingested": len(embeddings),
        "storage_path":    supa_path,
        "pinecone_index":  os.getenv("PINECONE_INDEX_NAME"),
    }
