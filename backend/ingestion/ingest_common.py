import os
import logging
from uuid import uuid4
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional
import asyncio

from core.config import get_settings
from core.deps import get_supabase
from data_upload.supabase_text_services import ingest_text_chunks
from data_upload.supabase_image_services import ingest_single_image
from data_upload.supabase_deep_embed_services import ingest_deep_embed_images
from ingestion.text.extract_text import extract_text_metadata, extract_text_and_images_metadata
from embed.embeddings import embed_texts, embed_images
from tagging.background_tasks import tag_uploaded_image_after_ingest
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


logger = logging.getLogger(__name__)

SUPPORTED_TEXT = ("docx", "pdf", "txt", "md")
SUPPORTED_IMAGES = ("png", "jpeg", "jpg", "webp")


async def ingest_file_content(
    file_content: bytes,
    filename: str,
    mime_type: str,
    user_id: str,
    supabase,
    settings,
    storage_path: str,
    extract_deep_embeds: bool = True,
    group_id: Optional[str] = None,
    storage_metadata: Optional[Dict[str, Any]] = None,
    doc_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Common ingestion logic for file content (text or image).
    
    Args:
        file_content: Raw file bytes
        filename: Original filename
        mime_type: File MIME type
        user_id: User ID for namespace
        supabase: Supabase client
        settings: App settings (requires TEXT_EMBED_DIM, IMAGE_EMBED_DIM, DEEP_IMAGE_EMBED_DIM env vars)
        storage_path: Path where file is/will be stored
        extract_deep_embeds: Whether to extract images from PDFs/docx
        group_id: Optional group ID for organization
        storage_metadata: Optional dict with storage provider info
        doc_id: Optional doc_id to use (generated if not provided)
    
    Returns:
        Dict with ingestion results
    """
    # Get embedding dimensions from environment variables (.env)
    try:
        text_embed_dim = int(os.environ.get('TEXT_EMBED_DIM', '384'))
    except ValueError:
        text_embed_dim = 384
        logger.warning("TEXT_EMBED_DIM not a valid integer, using default 384")
    
    try:
        image_embed_dim = int(os.environ.get('IMAGE_EMBED_DIM', '512'))
    except ValueError:
        image_embed_dim = 512
        logger.warning("IMAGE_EMBED_DIM not a valid integer, using default 512")
    
    try:
        deep_image_embed_dim = int(os.environ.get('DEEP_IMAGE_EMBED_DIM', '512'))
    except ValueError:
        deep_image_embed_dim = 512
        logger.warning("DEEP_IMAGE_EMBED_DIM not a valid integer, using default 512")
    
    logger.info(f"Using embedding dimensions - text: {text_embed_dim}, image: {image_embed_dim}, deep_image: {deep_image_embed_dim}")
    
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    
    if ext not in SUPPORTED_TEXT + SUPPORTED_IMAGES:
        raise ValueError(f"Unsupported file type: {ext or 'unknown'}")
    
    doc_id = doc_id or str(uuid4())
    logger.info(f"Ingesting file: {filename} (doc_id={doc_id}, ext={ext})")
    
    # --- Handle standalone images ---
    if ext in SUPPORTED_IMAGES:
        logger.info("Processing as standalone image")
        image_vectors = await embed_images([file_content])

        # Extract bucket from storage_path if available
        bucket = "images"  # default
        if storage_metadata and "bucket" in storage_metadata:
            bucket = storage_metadata["bucket"]

        result = ingest_single_image(
            supabase,
            user_id=user_id,
            filename=filename,
            storage_path=storage_path,
            file_bytes=file_content,
            mime_type=mime_type or "image/jpeg",
            embedding_model=settings.EMBED_MODEL,
            embedding_dim=image_embed_dim,
            embed_image_vectors=image_vectors,
            namespace=user_id,
            doc_id=doc_id,
            embedding_version=1,
            size_bytes=len(file_content),
            group_id=group_id,
            bucket=bucket,
        )

        # Trigger auto-tagging in the background for all uploaded images (including Google Drive)
        logger.info(f"Scheduling auto-tagging for uploaded image: doc_id={doc_id}, chunk_id={result['chunk_id']}")
        try:
            from tagging.background_tasks import tag_image_background
            # Schedule tagging without blocking the response, passing chunk_id directly
            asyncio.create_task(
                tag_image_background(
                    chunk_id=result["chunk_id"],
                    user_id=user_id,
                    doc_id=doc_id,
                    image_embedding=image_vectors[0],
                    storage_path=result["storage_path"],
                    bucket=result["bucket"]
                )
            )
        except Exception as e:
            logger.warning(f"Failed to schedule tagging task: {e}")

        logger.info(f"Image ingestion complete: doc_id={doc_id}")
        return {
            "doc_id": doc_id,
            "text_chunks_ingested": 0,
            "images_extracted": 1,
            "storage_type": "reference" if storage_metadata else "uploaded",
        }
    
    # --- Handle text/PDF/docx ---
    logger.info(f"Processing as document: {ext}")
    suffix = f".{ext}" if ext else ""
    
    with NamedTemporaryFile(prefix="ingest_", suffix=suffix, delete=False) as tmp:
        tmp.write(file_content)
        tmp_path = tmp.name
    
    logger.info(f"Created temp file: {tmp_path}")
    
    try:
        # Extract text and optionally images
        should_extract_images = extract_deep_embeds and ext in ("pdf", "docx")
        logger.info(f"Should extract images: {should_extract_images}")
        
        if should_extract_images:
            logger.info("Extracting text and images")
            meta_out = extract_text_and_images_metadata(
                file_path=tmp_path,
                user_id=user_id,
                max_chunk_size=800,
                chunk_overlap=20,
                extract_images=True,
                filter_important=True,
            )
        else:
            logger.info("Extracting text only")
            meta_out = extract_text_metadata(tmp_path, user_id=user_id, max_chunk_size=800)
            meta_out["images"] = []
        
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
        raise ValueError("No text chunks were extracted from file")
    
    # --- Embed and ingest text chunks ---
    logger.info("Embedding text chunks")
    texts = [c["chunk_text"] for c in chunks]
    text_vectors = await embed_texts(texts)
    logger.info(f"Generated {len(text_vectors)} text embeddings")
    logger.info(f"Text embedding model: {settings.EMBED_MODEL}")
    logger.info(f"Text embedding dim: {settings.EMBED_DIM}")
    if text_vectors:
        logger.info(f"Actual first vector shape: {len(text_vectors[0])}")
    
    extra_metas = [{
        "page_number": c.get("page_number"),
        "char_start": c.get("char_start"),
        "char_end": c.get("char_end"),
        "preview": (c.get("chunk_text") or "")[:180].replace("\n", " "),
    } for c in chunks]
    
    logger.info("Ingesting text chunks to Pinecone")
    try:
        text_result = ingest_text_chunks(
            supabase,
            user_id=user_id,
            filename=filename,
            storage_path=storage_path,
            text_chunks=texts,
            mime_type=mime_type or "application/octet-stream",
            embedding_model=settings.EMBED_MODEL,
            embedding_dim=text_embed_dim,
            embed_text_vectors=text_vectors,
            namespace=user_id,
            doc_id=doc_id,
            embedding_version=1,
            extra_vector_metadata=extra_metas,
            size_bytes=len(file_content),
            group_id=group_id,
        )
        logger.info(f"Text result type: {type(text_result)}")
        logger.info(f"Text result: {text_result}")
    except Exception as e:
        logger.error(f"CRITICAL ERROR in ingest_text_chunks: {e}", exc_info=True)
        raise
    
    # Update with storage metadata if provided
    if storage_metadata:
        try:
            supabase.table("app_chunks").update(storage_metadata).eq("doc_id", doc_id).execute()
            logger.info(f"Updated chunks with storage metadata")
        except Exception as e:
            logger.warning(f"Could not update storage metadata: {e}")
    
    # --- Embed and ingest extracted images ---
    images_result = None
    if images_data:
        logger.info(f"Starting image embedding for {len(images_data)} images")
        try:
            image_bytes_list = [img["image_bytes"] for img in images_data]
            image_vectors = await embed_images(image_bytes_list)
            logger.info(f"Generated {len(image_vectors)} image embeddings")

            logger.info("Ingesting deep embed images")
            images_result = ingest_deep_embed_images(
                supabase=supabase,
                user_id=user_id,
                doc_id=doc_id,
                parent_filename=filename,
                parent_storage_path=storage_path,
                images_data=images_data,
                embed_image_vectors=image_vectors,
                embedding_model=settings.EMBED_MODEL,
                embedding_dim=deep_image_embed_dim,
                namespace=user_id,
                embedding_version=1,
                group_id=group_id,
            )
            logger.info(f"Image ingestion complete: {images_result}")

            # NOTE: Auto-tagging disabled for images extracted from documents (PDFs/DOCX)
            # Only directly uploaded images are auto-tagged
            logger.info(f"Skipping auto-tagging for {len(images_data)} extracted images from document")

        except Exception as e:
            logger.error(f"Error during image ingestion: {e}", exc_info=True)
            logger.warning("Continuing despite image ingestion failure")
    else:
        logger.info("No images to ingest")
    
    logger.info(f"File ingestion complete: doc_id={doc_id}")
    
    # Safely extract vector count
    try:
        text_chunks_count = text_result.get("vector_count", 0) if isinstance(text_result, dict) else 0
        logger.info(f"Extracted text_chunks_count: {text_chunks_count}")
    except Exception as e:
        logger.error(f"Error extracting vector_count: {e}")
        text_chunks_count = 0
    
    try:
        images_extracted = images_result.get("images_ingested", 0) if images_result and isinstance(images_result, dict) else 0
        logger.info(f"Extracted images_extracted: {images_extracted}")
    except Exception as e:
        logger.error(f"Error extracting images_ingested: {e}")
        images_extracted = 0
    
    response = {
        "doc_id": str(doc_id),
        "text_chunks_ingested": int(text_chunks_count),
        "images_extracted": int(images_extracted),
        "storage_type": "reference" if storage_metadata else "uploaded",
    }
    logger.info(f"Returning response: {response}")
    return response