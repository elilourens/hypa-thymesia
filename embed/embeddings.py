# embed/embeddings.py
from typing import List, Union
from embed.text_embedder import embed as embed_text
from embed.image_embedder import embed as embed_image


async def embed_texts(texts: List[str]) -> List[List[float]]:
    return embed_text(texts)

async def embed_images(images: List[bytes]) -> List[List[float]]:
    return embed_image(images)


