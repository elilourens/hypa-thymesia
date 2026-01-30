# embed/clip_text_embedder.py
from typing import List
from sentence_transformers import SentenceTransformer

# Lazy global so model loads once per process
_model = None

def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        # Same checkpoint you used for images (shared 512-D space)
        _model = SentenceTransformer("clip-ViT-B-32")
    return _model

def embed(texts: List[str]) -> List[List[float]]:
    """
    Returns 512-D CLIP text embeddings for each input string.
    DO NOT use this for MiniLM text; this is only for text->image search.
    """
    model = _get_model()
    vecs = model.encode(texts, normalize_embeddings=False)  # keep raw CLIP space
    # Sentence-Transformers returns np.ndarray; convert to plain lists
    return [v.tolist() for v in vecs]
