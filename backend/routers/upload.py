import os
import logging
from uuid import uuid4
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Form
from core.config import get_settings
from core.deps import get_supabase
from core.security import get_current_user, AuthUser
from data_upload.supabase_text_services import upload_text_to_bucket, ingest_text_chunks
from data_upload.supabase_image_services import upload_image_to_bucket, ingest_single_image
from data_upload.supabase_deep_embed_services import ingest_deep_embed_images  # NEW
from ingestion.text.extract_text import extract_text_metadata, extract_text_and_images_metadata  # UPDATED
from embed.embeddings import embed_texts, embed_images

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingestion"])

@router.post("/upload-text-and-images")
async def ingest_text_and_image_files(
    file: UploadFile = File(...),
    group_id: Optional[str] = Form(None),
    extract_deep_embeds: bool = Form(True),  # NEW: toggle for deep embeds
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

    logger.info(f"Upload started: {file.filename}, size: {len(content)} bytes, extract_deep_embeds: {extract_deep_embeds}")

    if ext not in supported_text + supported_images:
        raise HTTPException(400, detail=f"Unsupported file type: {ext or 'unknown'}")

    # --- Handle standalone images ---
    if ext in supported_images:
        logger.info("Processing as standalone image")
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

    # --- Handle text/PDF/docx with deep embeds ---
    logger.info(f"Processing as document: {ext}")
    doc_id = str(uuid4())  # Generate doc_id once for both text and images
    logger.info(f"Generated doc_id: {doc_id}")
    
    storage_path = upload_text_to_bucket(
        content,
        file.filename,
        mime_type=file.content_type,
    )
    if not storage_path:
        raise HTTPException(500, detail="Failed to upload text to storage")
    
    logger.info(f"Uploaded to storage: {storage_path}")

    with NamedTemporaryFile(prefix="upload_", suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    
    logger.info(f"Created temp file: {tmp_path}")
    
    try:
        # UPDATED: Extract both text AND images
        should_extract_images = extract_deep_embeds and ext in ("pdf", "docx")
        logger.info(f"Should extract images: {should_extract_images} (ext={ext}, extract_deep_embeds={extract_deep_embeds})")
        
        if should_extract_images:
            logger.info("Calling extract_text_and_images_metadata")
            meta_out = extract_text_and_images_metadata(  # CHANGED
                file_path=tmp_path,
                user_id=user_id,
                max_chunk_size=800,
                chunk_overlap=20,
                extract_images=True,
                filter_important=True,
                
            )
        else:
            logger.info("Calling extract_text_metadata only")
            meta_out = extract_text_metadata(tmp_path, user_id=user_id, max_chunk_size=800)
            meta_out["images"] = []  # Ensure images key exists
        
        chunks: List[Dict[str, Any]] = meta_out.get("text_chunks", [])
        images_data: List[Dict[str, Any]] = meta_out.get("images", [])
        
        logger.info(f"Extraction complete: {len(chunks)} text chunks, {len(images_data)} images")
        
    finally:
        try:
            os.unlink(tmp_path)
            logger.info("Cleaned up temp file")
        except Exception as e:
            logger.warning(f"Failed to cleanup temp file: {e}")

    if not chunks:
        raise HTTPException(422, detail="No text chunks were extracted")

    # --- Embed and ingest text chunks ---
    logger.info("Embedding text chunks")
    texts = [c["chunk_text"] for c in chunks]
    text_vectors = await embed_texts(texts)
    logger.info(f"Generated {len(text_vectors)} text embeddings")

    extra_metas = [{
        "page_number": c.get("page_number"),
        "char_start": c.get("char_start"),
        "char_end": c.get("char_end"),
        "preview": (c.get("chunk_text") or "")[:180].replace("\n", " "),
    } for c in chunks]

    logger.info("Ingesting text chunks to Pinecone")
    text_result = ingest_text_chunks(
        user_id=user_id,
        filename=file.filename,
        storage_path=storage_path,
        text_chunks=texts,
        mime_type=file.content_type or "application/octet-stream",
        embedding_model="all-MiniLM-L12-v2",
        embedding_dim=384,
        embed_text_vectors=text_vectors,
        namespace=user_id,
        doc_id=doc_id,  # Use same doc_id
        embedding_version=1,
        extra_vector_metadata=extra_metas,
        size_bytes=len(content),
        group_id=group_id,
    )
    logger.info(f"Text ingestion complete: {text_result}")
    
    # --- NEW: Embed and ingest extracted images ---
    images_result = None
    if images_data:
        logger.info(f"Starting image embedding for {len(images_data)} images")
        try:
            # Embed the images using CLIP
            image_bytes_list = [img["image_bytes"] for img in images_data]
            image_vectors = await embed_images(image_bytes_list)
            logger.info(f"Generated {len(image_vectors)} image embeddings")
            
            # Upload to Supabase storage + Pinecone
            logger.info("Ingesting deep embed images")
            images_result = ingest_deep_embed_images(
                supabase=supabase,
                user_id=user_id,
                doc_id=doc_id,  # Same doc_id links them together
                parent_filename=file.filename,
                parent_storage_path=storage_path,
                images_data=images_data,
                embed_image_vectors=image_vectors,
                embedding_model=settings.EMBED_MODEL,
                embedding_dim=settings.EMBED_DIM,
                namespace=user_id,
                embedding_version=1,
                group_id=group_id,
            )
            logger.info(f"Image ingestion complete: {images_result}")
        except Exception as e:
            logger.error(f"Error during image ingestion: {e}", exc_info=True)
            # Don't fail entire upload if just images fail
            logger.warning("Continuing despite image ingestion failure")
    else:
        logger.info("No images to ingest")
    
    return {
        "doc_id": doc_id,
        "text_chunks_ingested": text_result["vector_count"],
        "images_extracted": images_result["images_ingested"] if images_result else 0,
    }
