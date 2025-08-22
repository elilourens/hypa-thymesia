# embed/embeddings.py
from typing import List, Union
from embed.text_embedder import embed as embed_text
from embed.image_embedder import embed as embed_image
from embed.clip_text_embedder import embed as embed_clip_text

async def embed_texts(texts: List[str]) -> List[List[float]]:
    return embed_text(texts)

async def embed_images(images: List[bytes]) -> List[List[float]]:
    return embed_image(images)

async def embed_clip_texts(texts: List[str]) -> List[List[float]]:
    # CLIP text (512-D) — used for text->image search against the image index
    return embed_clip_text(texts)

