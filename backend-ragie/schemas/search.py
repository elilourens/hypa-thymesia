"""Search-related Pydantic schemas."""

from typing import Optional
from pydantic import BaseModel


class SearchRequest(BaseModel):
    """Search/retrieval request."""

    query: str
    top_k: Optional[int] = 8
    rerank: Optional[bool] = True
    group_id: Optional[str] = None
    max_chunks_per_document: Optional[int] = 0
    modality: Optional[str] = None


class ScoredChunk(BaseModel):
    """A single scored chunk from retrieval."""

    text: str
    score: Optional[float] = None
    chunk_id: Optional[str] = None
    document_id: Optional[str] = None
    metadata: Optional[dict] = None


class SearchResponse(BaseModel):
    """Search/retrieval response."""

    scored_chunks: list[ScoredChunk]
    query: str
    total_chunks: int
