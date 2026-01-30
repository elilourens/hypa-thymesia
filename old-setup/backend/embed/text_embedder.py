# embed/text.py
from typing import List
from sentence_transformers import SentenceTransformer

_model = SentenceTransformer("all-MiniLM-L12-v2")

def embed(texts: List[str]) -> List[List[float]]:
    return _model.encode(texts, show_progress_bar=False).tolist()
