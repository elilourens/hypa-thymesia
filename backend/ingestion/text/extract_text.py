# ingestion/text/extract_text.py
from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List, Any, Tuple

from langchain_community.document_loaders import (
    PyMuPDFLoader,      # PDF via PyMuPDF
    Docx2txtLoader,     # DOCX
    TextLoader,         # TXT/MD
)
from langchain_text_splitters import RecursiveCharacterTextSplitter


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
    # PyMuPDFLoader sets {"page": int} (1-based). Others may not have page info.
    page = md.get("page")
    try:
        return int(page) if page is not None else None
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
        add_start_index=True,   # makes split_text return (text, start) pairs internally
        separators=["\n\n", "\n", " ", ""],  # Recursive behavior; same defaults
    )

    # Unfortunately split_documents() loses offsets. We mirror it using split_text()
    # and compute char_end = start + len(chunk_text).
    pieces = splitter.split_text(text)  # returns List[str] but uses internal indices
    # The public API doesn’t expose starts; we reconstruct deterministically by scanning.
    # Because RecursiveCharacterTextSplitter is deterministic, a linear scan works.

    results: List[Tuple[str, int, int]] = []
    cursor = 0
    for p in pieces:
        # find p from cursor onward to avoid matching earlier repeated text
        start = text.find(p, cursor)
        if start == -1:
            # rare fallback: search from beginning (can happen with aggressive overlaps/repeats)
            start = text.find(p)
        end = start + len(p) if start != -1 else None
        results.append((p, start if start != -1 else None, end))
        if start != -1:
            # advance cursor but respect overlap by not skipping too far
            # ensure we don't get stuck: move at least 1 char forward
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

    Returns:
        {
          "text_chunks": [
            {
              "chunk_text": str,
              "pdf_name": str,        # kept for backward-compat with your schema
              "page_number": int|None,
              "user_id": str,
              "timestamp": str (ISO-8601),
              "char_start": int|None, # offset within the source page/document text
              "char_end": int|None
            }, ...
          ]
        }
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError(f"Unsupported file type: {ext}")

    kind, loader = _pick_loader(file_path)
    docs = loader.load() or []  # PDF: one per page; others: typically one doc

    ts = datetime.utcnow().isoformat()
    name = _base_name_no_ext(file_path)

    out: List[Dict[str, Any]] = []

    # For each source doc (e.g., a PDF page), split and compute offsets relative to that doc’s text
    for src_doc in docs:
        src_text = (src_doc.page_content or "")
        if not src_text.strip():
            continue

        splits = _split_with_offsets(
            text=src_text,
            chunk_size=max_chunk_size,
            chunk_overlap=chunk_overlap,
        )

        page_num = _page_number_from_metadata(src_doc.metadata or {})

        for chunk_text, start, end in splits:
            if not chunk_text.strip():
                continue
            out.append({
                "chunk_text": chunk_text.strip(),
                "pdf_name": name,           # yes, kept for compat even if not a PDF
                "page_number": page_num,    # None for DOCX/TXT where unknown
                "user_id": user_id,
                "timestamp": ts,
                "char_start": start,
                "char_end": end,
            })

    return {"text_chunks": out}
