"""
Pydantic schemas for formatting API requests and responses.
"""

from typing import Optional
from pydantic import BaseModel, Field


class FormatChunkRequest(BaseModel):
    """Request to format a single text chunk."""
    text: str = Field(..., description="The text chunk to format")


class FormatChunkResponse(BaseModel):
    """Response from single chunk formatting."""
    original_text: str
    formatted_text: Optional[str]
    success: bool
    error: Optional[str] = None


class BatchFormatRequest(BaseModel):
    """Request to format multiple text chunks."""
    chunks: list[dict] = Field(
        ...,
        description="List of chunks with 'chunk_id' and 'text' fields"
    )
    max_concurrent: Optional[int] = Field(
        default=10,
        description="Maximum concurrent formatting requests"
    )


class ChunkResult(BaseModel):
    """Result for a single chunk in batch formatting."""
    chunk_id: str
    original_text: str
    formatted_text: Optional[str]
    success: bool
    error: Optional[str] = None


class BatchFormatResponse(BaseModel):
    """Response from batch chunk formatting."""
    total_chunks: int
    formatted: int
    failed: int
    results: list[ChunkResult]


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    ollama_connected: bool
    ollama_model: str
    error: Optional[str] = None
