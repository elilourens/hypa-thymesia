# app/routers/embed.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Literal, Union
from embed.embeddings import (
    embed_texts,
    embed_images,
)

router = APIRouter(prefix="/embed", tags=["embeddings"])


class EmbedRequest(BaseModel):
    type: Literal["text", "image", "audio", "video"]
    items: List[Union[str, bytes]]  # strings for text, raw bytes for media


@router.post("/")
async def embed(req: EmbedRequest):
    if not req.items:
        raise HTTPException(422, detail="No items provided")

    if req.type == "text":
        vectors = await embed_texts(req.items)            # items are List[str]
    elif req.type == "image":
        vectors = await embed_images(req.items)           # items are List[bytes]
    else:
        raise HTTPException(400, detail="Unsupported embed type")

    return {"embeddings": vectors}
