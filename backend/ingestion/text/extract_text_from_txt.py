from typing import List, Dict, Any
from datetime import datetime
import os

def extract_txt_text_metadata(txt_path: str, user_id: str, max_chunk_size: int = 800) -> Dict[str, List[Dict[str, Any]]]:
    txt_name = os.path.basename(txt_path).replace(".txt", "")
    timestamp = datetime.utcnow().isoformat()

    with open(txt_path, "r", encoding="utf-8") as f:
        text = f.read().strip()

    text_chunks = []

    for i in range(0, len(text), max_chunk_size):
        chunk = text[i:i + max_chunk_size]
        text_chunks.append({
            "chunk_text": chunk,
            "txt_name": txt_name,
            "user_id": user_id,
            "timestamp": timestamp
        })

    return {
        "text_chunks": text_chunks
    }
