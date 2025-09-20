import os
from uuid import uuid4
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Form
from core.config import get_settings
from core.deps import get_supabase
from core.security import get_current_user, AuthUser
from data_upload.supabase_text_services import upload_text_to_bucket, ingest_text_chunks
from data_upload.supabase_image_services import upload_image_to_bucket, ingest_single_image
from ingestion.text.extract_text import extract_text_metadata
from embed.embeddings import embed_texts, embed_images

router = APIRouter(prefix="/ingest", tags=["ingestion"])

@router.post("/upload-text-and-images")
async def ingest_text_and_image_files(
    file: UploadFile = File(...),
    group_id: Optional[str] = Form(None),
    auth: AuthUser = Depends(get_current_user),
    supabase = Depends(get_supabase),
    settings = Depends(get_settings),
):
    user_id = auth.id
    content = await file.read()
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    suffix = f".{ext}" if ext else ""
    supported_text = ("docx", "pdf", "txt", "md")
    supported_images = ("png", "jpeg", "jpg", "webp")

    if ext not in supported_text + supported_images:
        raise HTTPException(400, detail=f"Unsupported file type: {ext or 'unknown'}")

    # --- Handle images ---
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
            embedding_model=settings.EMBED_MODEL,
            embedding_dim=settings.EMBED_DIM,
            embed_image_vectors=image_vectors,
            namespace=user_id,
            doc_id=str(uuid4()),
            embedding_version=1,
            size_bytes=len(content),
            group_id=group_id,
        )
        return {"doc_id": result["doc_id"], "chunks_ingested": result["vector_count"]}

    # --- Handle text/PDF/docx ---
    storage_path = upload_text_to_bucket(
        content,
        file.filename,
        mime_type=file.content_type,   # 👈 pass correct MIME
    )
    if not storage_path:
        raise HTTPException(500, detail="Failed to upload text to storage")

    with NamedTemporaryFile(prefix="upload_", suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        meta_out = extract_text_metadata(tmp_path, user_id=user_id, max_chunk_size=800)
        chunks: List[Dict[str, Any]] = meta_out.get("text_chunks", [])
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    if not chunks:
        raise HTTPException(422, detail="No text chunks were extracted")

    texts = [c["chunk_text"] for c in chunks]
    text_vectors = await embed_texts(texts)

    extra_metas = [{
        "page_number": c.get("page_number"),
        "char_start": c.get("char_start"),
        "char_end": c.get("char_end"),
        "preview": (c.get("chunk_text") or "")[:180].replace("\n", " "),
    } for c in chunks]

    result = ingest_text_chunks(
        user_id=user_id,
        filename=file.filename,
        storage_path=storage_path,
        text_chunks=texts,
        mime_type=file.content_type or "application/octet-stream",  # 👈 keep real MIME
        embedding_model="all-MiniLM-L12-v2",
        embedding_dim=384,
        embed_text_vectors=text_vectors,
        namespace=user_id,
        doc_id=str(uuid4()),
        embedding_version=1,
        extra_vector_metadata=extra_metas,
        size_bytes=len(content),
        group_id=group_id,
    )
    return {"doc_id": result["doc_id"], "chunks_ingested": result["vector_count"]}
