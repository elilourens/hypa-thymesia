# embed/image.py
from typing import List
from PIL import Image
import io
import numpy as np
from sentence_transformers import SentenceTransformer

# e.g. use a CLIP-like model from SentenceTransformers
_model = SentenceTransformer("clip-ViT-B-32")

def embed(images: List[bytes]) -> List[List[float]]:
    """
    :param images: list of raw image bytes (e.g. PNG/JPEG)
    :return: list of embeddings
    """
    pil_images = [Image.open(io.BytesIO(b)) for b in images]
    # model.encode accepts PIL images for CLIP
    embeddings = _model.encode(pil_images, show_progress_bar=False)
    return embeddings.tolist()
