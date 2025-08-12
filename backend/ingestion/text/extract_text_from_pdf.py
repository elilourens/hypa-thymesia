import fitz  # PyMuPDF
from typing import List, Dict, Any
from datetime import datetime
import os

def extract_pdf_text_metadata(pdf_path: str, user_id: str, max_chunk_size: int = 800) -> Dict[str, List[Dict[str, Any]]]:
    doc = fitz.open(pdf_path)
    pdf_name = os.path.basename(pdf_path).replace(".pdf", "")
    timestamp = datetime.utcnow().isoformat()
    
    text_chunks = []

    for page_num, page in enumerate(doc):
        page_number = page_num + 1
        text = page.get_text().strip()

        if not text:
            continue

        # Break text into 800-character chunks
        for i in range(0, len(text), max_chunk_size):
            chunk_text = text[i:i + max_chunk_size]
            text_chunks.append({
                "chunk_text": chunk_text,
                "pdf_name": pdf_name,
                "page_number": page_number,
                "user_id": user_id,
                "timestamp": timestamp
                # "embedding": <embed separately>
            })

    return {
        "text_chunks": text_chunks
    }
