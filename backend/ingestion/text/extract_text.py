# ingestion/text/extract_text.py
from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import Dict, List, Any, Tuple
from PIL import Image
import io
import fitz  # PyMuPDF - add to requirements.txt
from docx import Document  # python-docx - add to requirements.txt

from langchain_community.document_loaders import (
    PyMuPDFLoader,      # PDF via PyMuPDF
    Docx2txtLoader,     # DOCX
    TextLoader,         # TXT/MD
)
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Set up logging
logger = logging.getLogger(__name__)

SUPPORTED_EXTS = {".pdf", ".docx", ".txt", ".md"}


def _pick_loader(file_path: str):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return ("pdf", PyMuPDFLoader(file_path))
    elif ext == ".docx":
        return ("docx", Docx2txtLoader(file_path))
    elif ext in {".txt", ".md"}:
        return ("text", TextLoader(file_path, encoding="utf-8", autodetect_encoding=True))
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def _base_name_no_ext(path: str) -> str:
    return os.path.basename(path).rsplit(".", 1)[0]


def _page_number_from_metadata(md: Dict[str, Any]) -> int | None:
    page = md.get("page")
    try:
        if page is not None:
            return int(page) + 1  # convert from 0-based → 1-based
        return None
    except Exception:
        return None


def _split_with_offsets(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> List[Tuple[str, int, int]]:
    """
    Split `text` into chunks using the same logic as RecursiveCharacterTextSplitter
    (character-based), but also return (chunk_text, char_start, char_end).
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        add_start_index=True,
        separators=["\n\n", "\n", " ", ""],
    )

    pieces = splitter.split_text(text)

    results: List[Tuple[str, int, int]] = []
    cursor = 0
    for p in pieces:
        start = text.find(p, cursor)
        if start == -1:
            start = text.find(p)
        end = start + len(p) if start != -1 else None
        results.append((p, start if start != -1 else None, end))
        if start != -1:
            cursor = max(cursor + 1, end - chunk_overlap if end is not None else cursor + len(p))
    return results


def extract_text_metadata(
    file_path: str,
    user_id: str,
    max_chunk_size: int = 800,
    chunk_overlap: int = 20,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Generic extractor using LangChain loaders with character overlap and offsets.
    """
    logger.info(f"Starting text extraction from: {file_path}")
    
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        raise FileNotFoundError(file_path)

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED_EXTS:
        logger.error(f"Unsupported file type: {ext}")
        raise ValueError(f"Unsupported file type: {ext}")

    logger.info(f"File extension: {ext}")
    kind, loader = _pick_loader(file_path)
    logger.info(f"Using loader: {kind}")
    
    docs = loader.load() or []
    logger.info(f"Loaded {len(docs)} document(s)")

    ts = datetime.utcnow().isoformat()
    name = _base_name_no_ext(file_path)

    out: List[Dict[str, Any]] = []

    for idx, src_doc in enumerate(docs):
        src_text = (src_doc.page_content or "")
        if not src_text.strip():
            logger.debug(f"Skipping empty document {idx}")
            continue

        splits = _split_with_offsets(
            text=src_text,
            chunk_size=max_chunk_size,
            chunk_overlap=chunk_overlap,
        )

        page_num = _page_number_from_metadata(src_doc.metadata or {})
        logger.debug(f"Document {idx}: page_num={page_num}, splits={len(splits)}")

        for chunk_text, start, end in splits:
            if not chunk_text.strip():
                continue
            out.append({
                "chunk_text": chunk_text.strip(),
                "pdf_name": name,
                "page_number": page_num,
                "user_id": user_id,
                "timestamp": ts,
                "char_start": start,
                "char_end": end,
            })

    logger.info(f"Extracted {len(out)} text chunks")
    return {"text_chunks": out}


# ==================== Image Extraction Functions ====================

def is_important_image(
    image: Image.Image,
    min_width: int = 150,
    min_height: int = 150,
    max_aspect_ratio: float = 3.0,
) -> bool:
    """Filter out icons, lines, decorative elements."""
    width, height = image.size
    
    if width < min_width or height < min_height:
        logger.debug(f"Image filtered: too small ({width}x{height})")
        return False
    
    aspect_ratio = max(width, height) / min(width, height)
    if aspect_ratio > max_aspect_ratio:
        logger.debug(f"Image filtered: aspect ratio too extreme ({aspect_ratio:.2f})")
        return False
    
    logger.debug(f"Image passed filter: {width}x{height}, aspect ratio {aspect_ratio:.2f}")
    return True


def extract_images_from_pdf(
    file_path: str,
    user_id: str,
    filter_important: bool = True,
) -> List[Dict[str, Any]]:
    """Extract images from PDF using PyMuPDF."""
    logger.info(f"Starting PDF image extraction from: {file_path}")
    logger.info(f"Filter important: {filter_important}")
    
    doc = fitz.open(file_path)
    doc_name = _base_name_no_ext(file_path)
    ts = datetime.utcnow().isoformat()
    
    logger.info(f"PDF has {len(doc)} pages")
    
    images = []
    total_images_found = 0
    images_passed_filter = 0
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images(full=True)
        
        logger.info(f"Page {page_num + 1}: Found {len(image_list)} image(s)")
        
        for img_index, img_info in enumerate(image_list):
            total_images_found += 1
            xref = img_info[0]
            
            try:
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                
                pil_image = Image.open(io.BytesIO(image_bytes))
                logger.debug(f"  Image {img_index}: {pil_image.width}x{pil_image.height}, format: {base_image['ext']}")
                
                # Check filter
                passed_filter = True
                if filter_important:
                    passed_filter = is_important_image(pil_image)
                
                if not passed_filter:
                    logger.debug(f"  Skipping image {img_index} (filtered out)")
                    continue
                
                images_passed_filter += 1
                
                # Get image position on page
                img_rects = page.get_image_rects(xref)
                bbox = img_rects[0] if img_rects else None
                
                images.append({
                    "image_bytes": image_bytes,
                    "pil_image": pil_image,
                    "page_number": page_num + 1,  # 1-based
                    "image_index": img_index,
                    "doc_name": doc_name,
                    "user_id": user_id,
                    "timestamp": ts,
                    "width": pil_image.width,
                    "height": pil_image.height,
                    "format": base_image["ext"],
                    "bbox": bbox,
                })
                
                logger.info(f"  ✅ Kept image {img_index}: {pil_image.width}x{pil_image.height}")
                
            except Exception as e:
                logger.error(f"  ❌ Error processing image {img_index} on page {page_num + 1}: {e}")
                continue
    
    doc.close()
    
    logger.info(f"PDF extraction complete:")
    logger.info(f"  - Total images found: {total_images_found}")
    logger.info(f"  - Images passed filter: {images_passed_filter}")
    logger.info(f"  - Images filtered out: {total_images_found - images_passed_filter}")
    
    return images


def extract_images_from_docx(
    file_path: str,
    user_id: str,
    filter_important: bool = True,
) -> List[Dict[str, Any]]:
    """Extract images from DOCX."""
    logger.info(f"Starting DOCX image extraction from: {file_path}")
    logger.info(f"Filter important: {filter_important}")
    
    doc = Document(file_path)
    doc_name = _base_name_no_ext(file_path)
    ts = datetime.utcnow().isoformat()
    
    images = []
    image_index = 0
    total_images_found = 0
    images_passed_filter = 0
    
    logger.info(f"Scanning DOCX relationships for images...")
    
    for rel_id, rel in doc.part.rels.items():
        if "image" in rel.target_ref:
            total_images_found += 1
            image_bytes = rel.target_part.blob
            
            try:
                pil_image = Image.open(io.BytesIO(image_bytes))
                logger.debug(f"Image {image_index}: {pil_image.width}x{pil_image.height}")
                
                # Check filter
                passed_filter = True
                if filter_important:
                    passed_filter = is_important_image(pil_image)
                
                if not passed_filter:
                    logger.debug(f"  Skipping image {image_index} (filtered out)")
                    image_index += 1
                    continue
                
                images_passed_filter += 1
                
                images.append({
                    "image_bytes": image_bytes,
                    "pil_image": pil_image,
                    "page_number": None,  # DOCX doesn't have reliable pages
                    "image_index": image_index,
                    "doc_name": doc_name,
                    "user_id": user_id,
                    "timestamp": ts,
                    "width": pil_image.width,
                    "height": pil_image.height,
                    "format": rel.target_ref.split('.')[-1],
                    "bbox": None,
                })
                
                logger.info(f"  ✅ Kept image {image_index}: {pil_image.width}x{pil_image.height}")
                image_index += 1
                
            except Exception as e:
                logger.error(f"  ❌ Error extracting image {rel_id}: {e}")
                continue
    
    logger.info(f"DOCX extraction complete:")
    logger.info(f"  - Total images found: {total_images_found}")
    logger.info(f"  - Images passed filter: {images_passed_filter}")
    logger.info(f"  - Images filtered out: {total_images_found - images_passed_filter}")
    
    return images


def extract_text_and_images_metadata(
    file_path: str,
    user_id: str,
    max_chunk_size: int = 800,
    chunk_overlap: int = 20,
    extract_images: bool = True,
    filter_important: bool = True,
) -> Dict[str, Any]:
    """
    Extract both text chunks AND images from document.
    
    Args:
        file_path: Path to document
        user_id: User ID
        max_chunk_size: Max characters per text chunk
        chunk_overlap: Character overlap between chunks
        extract_images: Whether to extract images
        filter_important: Whether to filter out small/decorative images (min 150x150)
    
    Returns:
        {
          "text_chunks": [...],  # existing format
          "images": [...],       # new: extracted images
        }
    """
    logger.info("="*60)
    logger.info(f"extract_text_and_images_metadata called")
    logger.info(f"  file_path: {file_path}")
    logger.info(f"  extract_images: {extract_images}")
    logger.info(f"  filter_important: {filter_important}")
    logger.info("="*60)
    
    # Get text chunks (existing logic)
    result = extract_text_metadata(file_path, user_id, max_chunk_size, chunk_overlap)
    
    # Extract images if requested
    if extract_images:
        ext = os.path.splitext(file_path)[1].lower()
        logger.info(f"Extracting images for file type: {ext}")
        
        if ext == ".pdf":
            images = extract_images_from_pdf(file_path, user_id, filter_important)
            result["images"] = images
        elif ext == ".docx":
            images = extract_images_from_docx(file_path, user_id, filter_important)
            result["images"] = images
        else:
            logger.info(f"No image extraction for file type: {ext}")
            result["images"] = []
    else:
        logger.info("Image extraction disabled")
        result["images"] = []
    
    logger.info(f"Final result: {len(result.get('text_chunks', []))} text chunks, {len(result.get('images', []))} images")
    logger.info("="*60)
    
    return result