import os
import logging
from uuid import uuid4
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from core.config import get_settings
from core.deps import get_supabase
from core.security import get_current_user, AuthUser
from data_upload.supabase_text_services import upload_text_to_bucket, ingest_text_chunks
from data_upload.supabase_image_services import upload_image_to_bucket, ingest_single_image
from data_upload.supabase_deep_embed_services import ingest_deep_embed_images
from ingestion.text.extract_text import extract_text_metadata, extract_text_and_images_metadata
from embed.embeddings import embed_texts, embed_images
import requests
import re

logger = logging.getLogger(__name__)
router = APIRouter(tags=["google_drive"])

class IngestGoogleDriveFileRequest(BaseModel):
    google_drive_id: str
    google_drive_url: str
    filename: str
    mime_type: str
    size_bytes: int
    group_id: Optional[str] = None
    extract_deep_embeds: bool = True

def download_google_drive_file(file_id: str, url: str) -> bytes:
    """
    Download a file from Google Drive, handling confirmation pages.
    """
    logger.info(f"Starting Google Drive download for file: {file_id}")
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    
    try:
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        logger.info(f"Initial request to: {download_url}")
        
        response = session.get(download_url, timeout=60, stream=True, allow_redirects=True)
        response.raise_for_status()
        
        content_type = response.headers.get('content-type', '').lower()
        logger.info(f"Response content-type: {content_type}")
        
        if 'text/html' in content_type:
            logger.info("Received HTML, searching for confirmation token...")
            
            html_text = response.text
            patterns = [
                r'"confirm"\s*:\s*"([^"]+)"',
                r'confirm["\']?\s*:\s*["\']([^"\']+)["\']',
                r'id=["\']([^"\']+)["\']',
                r'(?:uuid|token)["\']?\s*:\s*["\']([a-zA-Z0-9_-]+)["\']',
            ]
            
            token = None
            for pattern in patterns:
                match = re.search(pattern, html_text, re.IGNORECASE)
                if match:
                    token = match.group(1)
                    logger.info(f"Found token with pattern: {pattern[:30]}...")
                    break
            
            if not token:
                logger.warning("Standard patterns failed, searching for token-like strings...")
                matches = re.findall(r'[a-zA-Z0-9_-]{20,}', html_text)
                if matches:
                    token = matches[0]
                    logger.info(f"Using fallback token: {token[:20]}...")
            
            if token:
                download_url_with_token = f"https://drive.google.com/uc?export=download&id={file_id}&confirm={token}"
                logger.info(f"Retrying with token in URL...")
                
                response = session.get(download_url_with_token, timeout=60, stream=True, allow_redirects=True)
                response.raise_for_status()
                
                content_type_retry = response.headers.get('content-type', '').lower()
                logger.info(f"Retry response content-type: {content_type_retry}")
            else:
                logger.warning("Could not extract token, proceeding with current response...")
        
        content = b''
        chunk_count = 0
        
        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                content += chunk
                chunk_count += 1
                if chunk_count % 10 == 0:
                    logger.info(f"Downloaded {len(content)} bytes...")
        
        logger.info(f"Download complete: {len(content)} bytes total")
        
        if len(content) < 10:
            logger.error(f"Downloaded content too small: {len(content)} bytes")
            raise Exception(f"File too small ({len(content)} bytes) - may be invalid")
        
        if content.startswith(b'<!DOCTYPE') or content.startswith(b'<html') or content.startswith(b'<HTML'):
            logger.error("Downloaded content is HTML, not a file")
            logger.debug(f"Content preview: {content[:500]}")
            raise Exception("Downloaded content is HTML - file may not be publicly shareable or require authentication")
        
        logger.info(f"✓ Successfully downloaded valid file: {len(content)} bytes")
        return content
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error during download: {e}")
        raise Exception(f"Network error: {str(e)}")
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise
    finally:
        session.close()

@router.post("/ingest-google-drive-file")
async def ingest_google_drive_file(
    auth: AuthUser = Depends(get_current_user),
    supabase = Depends(get_supabase),
    settings = Depends(get_settings),
    request: IngestGoogleDriveFileRequest = Body(...)
):
    """
    Ingest a Google Drive file by storing a reference instead of uploading it.
    For images: Store reference + embed to Pinecone
    For documents: Extract text, store reference, embed text to Pinecone
    """
    user_id = auth.id
    logger.info(f"Ingesting Google Drive file: {request.filename} (ID: {request.google_drive_id})")

    # --- Download file from Google Drive ---
    try:
        logger.info(f"Starting download from Google Drive: {request.google_drive_url}")
        content = download_google_drive_file(request.google_drive_id, request.google_drive_url)
        logger.info(f"Successfully downloaded {len(content)} bytes from Google Drive")
        
    except Exception as e:
        logger.error(f"Failed to download from Google Drive: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to download file from Google Drive: {str(e)}")

    # --- Determine file type ---
    ext = request.filename.rsplit(".", 1)[-1].lower() if "." in request.filename else ""
    suffix = f".{ext}" if ext else ""
    supported_text = ("docx", "pdf", "txt", "md")
    supported_images = ("png", "jpeg", "jpg", "webp")

    if ext not in supported_text + supported_images:
        raise HTTPException(400, detail=f"Unsupported file type: {ext or 'unknown'}")

    logger.info(f"File type: {ext}, MIME: {request.mime_type}")

    # --- Generate doc_id once for all entries ---
    doc_id = str(uuid4())
    logger.info(f"Generated doc_id: {doc_id}")

    # --- Use a virtual reference path with FILENAME included ---
    # Format: google-drive/{file_id}/{filename}
    # This way when app_docs view extracts filename with regexp_replace, it gets the actual name
    storage_path = f"google-drive/{request.google_drive_id}/{request.filename}"
    bucket = "google-drive"  # Virtual bucket name

    # --- Handle standalone images (store as reference) ---
    if ext in supported_images:
        logger.info("Processing Google Drive file as standalone image (reference only)")
        
        try:
            logger.info(f"Embedding image for Pinecone...")
            image_vectors = await embed_images([content])
            
            # Ingest to Pinecone with Google Drive reference
            logger.info(f"Storing Google Drive image reference")
            
            result = ingest_single_image(
                user_id=user_id,
                filename=request.filename,
                storage_path=storage_path,
                file_bytes=content,  # Used for embedding only
                mime_type=request.mime_type or "image/jpeg",
                embedding_model=settings.EMBED_MODEL,
                embedding_dim=settings.EMBED_DIM,
                embed_image_vectors=image_vectors,
                namespace=user_id,
                doc_id=doc_id,
                embedding_version=1,
                size_bytes=len(content),
                group_id=request.group_id,
            )
            
            # Update the chunk records with Google Drive metadata
            try:
                supabase.table("app_chunks").update({
                    "storage_provider": "google_drive",
                    "external_id": request.google_drive_id,
                    "external_url": request.google_drive_url,
                    "bucket": bucket,
                }).eq("doc_id", doc_id).execute()
                logger.info(f"Updated chunk metadata with Google Drive reference and filename in storage_path")
            except Exception as e:
                logger.warning(f"Could not update Google Drive metadata: {e}")
            
            logger.info(f"Image reference stored: doc_id={doc_id}")
            return {
                "doc_id": doc_id,
                "text_chunks_ingested": 0,
                "images_extracted": 1,
                "source": "google_drive",
                "storage_type": "reference"
            }
        except Exception as e:
            logger.error(f"Error processing image: {e}", exc_info=True)
            raise HTTPException(500, detail=f"Error processing image: {str(e)}")

    # --- Handle text/PDF/docx (reference + embeddings) ---
    logger.info(f"Processing Google Drive file as document: {ext}")

    # Create temp file for extraction
    with NamedTemporaryFile(prefix="google_drive_", suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    
    logger.info(f"Created temp file: {tmp_path}")
    
    try:
        # Extract text and optionally images
        should_extract_images = request.extract_deep_embeds and ext in ("pdf", "docx")
        logger.info(f"Should extract images: {should_extract_images}")
        
        if should_extract_images:
            logger.info("Extracting text and images from Google Drive file")
            meta_out = extract_text_and_images_metadata(
                file_path=tmp_path,
                user_id=user_id,
                max_chunk_size=800,
                chunk_overlap=20,
                extract_images=True,
                filter_important=True,
            )
        else:
            logger.info("Extracting text only from Google Drive file")
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
        raise HTTPException(422, detail="No text chunks were extracted from Google Drive file")

    # --- Embed and ingest text chunks ---
    logger.info("Embedding text chunks from Google Drive file")
    texts = [c["chunk_text"] for c in chunks]
    text_vectors = await embed_texts(texts)
    logger.info(f"Generated {len(text_vectors)} text embeddings")

    extra_metas = [{
        "page_number": c.get("page_number"),
        "char_start": c.get("char_start"),
        "char_end": c.get("char_end"),
        "preview": (c.get("chunk_text") or "")[:180].replace("\n", " "),
    } for c in chunks]

    logger.info("Ingesting text chunks to Pinecone (with Google Drive reference)")
    text_result = ingest_text_chunks(
        user_id=user_id,
        filename=request.filename,
        storage_path=storage_path,
        text_chunks=texts,
        mime_type=request.mime_type or "application/octet-stream",
        embedding_model=settings.EMBED_MODEL,
        embedding_dim=settings.EMBED_DIM,
        embed_text_vectors=text_vectors,
        namespace=user_id,
        doc_id=doc_id,
        embedding_version=1,
        extra_vector_metadata=extra_metas,
        size_bytes=len(content),
        group_id=request.group_id,
    )
    logger.info(f"Text ingestion complete: {text_result}")
    
    # Update chunks to mark as Google Drive reference
    try:
        supabase.table("app_chunks").update({
            "storage_provider": "google_drive",
            "external_id": request.google_drive_id,
            "external_url": request.google_drive_url,
            "bucket": bucket,
        }).eq("doc_id", doc_id).execute()
        logger.info(f"Updated text chunks with Google Drive reference metadata and filename in storage_path")
    except Exception as e:
        logger.warning(f"Could not update Google Drive metadata: {e}")
    
    # --- Embed and ingest extracted images ---
    images_result = None
    if images_data:
        logger.info(f"Starting image embedding for {len(images_data)} extracted images from Google Drive file")
        try:
            image_bytes_list = [img["image_bytes"] for img in images_data]
            image_vectors = await embed_images(image_bytes_list)
            logger.info(f"Generated {len(image_vectors)} image embeddings")
            
            logger.info("Ingesting deep embed images from Google Drive file")
            images_result = ingest_deep_embed_images(
                supabase=supabase,
                user_id=user_id,
                doc_id=doc_id,
                parent_filename=request.filename,
                parent_storage_path=storage_path,
                images_data=images_data,
                embed_image_vectors=image_vectors,
                embedding_model=settings.EMBED_MODEL,
                embedding_dim=settings.EMBED_DIM,
                namespace=user_id,
                embedding_version=1,
                group_id=request.group_id,
            )
            logger.info(f"Image ingestion complete: {images_result}")
        except Exception as e:
            logger.error(f"Error during image ingestion: {e}", exc_info=True)
            logger.warning("Continuing despite image ingestion failure")
    else:
        logger.info("No images to ingest")
    
    logger.info(f"Google Drive file ingestion complete: doc_id={doc_id}")
    return {
        "doc_id": doc_id,
        "text_chunks_ingested": text_result["vector_count"],
        "images_extracted": images_result["images_ingested"] if images_result else 0,
        "source": "google_drive",
        "storage_type": "reference"
    }