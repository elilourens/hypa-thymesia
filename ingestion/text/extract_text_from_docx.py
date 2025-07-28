from docx import Document
from typing import List, Dict, Any
from datetime import datetime
import os

def extract_docx_text_metadata(docx_path: str, user_id: str) -> Dict[str, List[Dict[str, Any]]]:
    doc = Document(docx_path)
    docx_name = os.path.basename(docx_path).replace(".docx", "")
    timestamp = datetime.utcnow().isoformat()
    
    text_chunks = []
    current_chunk = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        current_chunk.append(text)

        # Optional: chunk on blank lines or max character count
        if len(" ".join(current_chunk)) > 800:  # You can tune this threshold
            chunk_text = " ".join(current_chunk)
            text_chunks.append({
                "chunk_text": chunk_text,
                "docx_name": docx_name,
                "user_id": user_id,
                "timestamp": timestamp
                # "embedding": <embed separately>
            })
            current_chunk = []

    # Add any remaining chunk
    if current_chunk:
        chunk_text = " ".join(current_chunk)
        text_chunks.append({
            "chunk_text": chunk_text,
            "docx_name": docx_name,
            "user_id": user_id,
            "timestamp": timestamp
        })

    return {
        "text_chunks": text_chunks
    }
