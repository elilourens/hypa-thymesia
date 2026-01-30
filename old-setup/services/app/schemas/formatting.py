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


# ============================================================================
# Document Tagging Schemas
# ============================================================================

class DocumentTag(BaseModel):
    """A single document tag with metadata."""
    tag_name: str
    category: str
    confidence: float
    reasoning: Optional[str] = None


class TagDocumentRequest(BaseModel):
    """Request to tag a document."""
    text_content: str = Field(..., description="Full text content of the document")
    filename: str = Field(default="", description="Original filename for context")
    min_confidence: float = Field(default=0.5, description="Minimum confidence threshold")


class TagDocumentResponse(BaseModel):
    """Response from document tagging."""
    tags: list[DocumentTag]
    processing_time_ms: float
    preview_chars: int
    total_chars: int
    total_tags: int
    filtered_tags: int
    success: bool
    error: Optional[str] = None


class BatchTagDocRequest(BaseModel):
    """Request to tag multiple documents."""
    documents: list[dict] = Field(
        ...,
        description="List of documents with 'doc_id', 'text_content', and optional 'filename' fields"
    )
    min_confidence: float = Field(default=0.5, description="Minimum confidence threshold")
    max_concurrent: Optional[int] = Field(default=6, description="Maximum concurrent tagging requests")


class DocTagResult(BaseModel):
    """Result for a single document in batch tagging."""
    doc_id: str
    tags: list[DocumentTag]
    processing_time_ms: float
    success: bool
    error: Optional[str] = None


class BatchTagDocResponse(BaseModel):
    """Response from batch document tagging."""
    total_documents: int
    successful: int
    failed: int
    results: list[DocTagResult]


# ============================================================================
# Image Tagging Schemas
# ============================================================================

class BoundingBox(BaseModel):
    """Bounding box for detected object."""
    x: int
    y: int
    width: int
    height: int


class ImageTag(BaseModel):
    """A single image tag with metadata."""
    label: str
    confidence: float
    bbox: Optional[BoundingBox] = None
    verified: bool = False


class TagImageRequest(BaseModel):
    """Request to tag a single image."""
    image_embedding: list[float] = Field(..., description="Pre-computed CLIP embedding (512D)")
    image_base64: str = Field(..., description="Base64-encoded image bytes")
    clip_top_k: int = Field(default=15, description="Number of CLIP candidates to generate")
    clip_min_confidence: float = Field(default=0.15, description="Minimum CLIP confidence threshold")
    owlvit_min_confidence: float = Field(default=0.15, description="Minimum OWL-ViT confidence threshold")


class TagImageResponse(BaseModel):
    """Response from image tagging."""
    verified_tags: list[ImageTag]
    candidate_tags: list[ImageTag]
    processing_time_ms: float
    success: bool
    error: Optional[str] = None


class BatchTagImageRequest(BaseModel):
    """Request to tag multiple images."""
    images: list[dict] = Field(
        ...,
        description="List of images with 'image_id', 'image_embedding', and 'image_base64' fields"
    )
    clip_top_k: int = Field(default=15, description="Number of CLIP candidates per image")
    clip_min_confidence: float = Field(default=0.15, description="Minimum CLIP confidence")
    owlvit_min_confidence: float = Field(default=0.15, description="Minimum OWL-ViT confidence")
    max_concurrent: Optional[int] = Field(default=4, description="Maximum concurrent tagging requests")


class ImageTagResult(BaseModel):
    """Result for a single image in batch tagging."""
    image_id: str
    verified_tags: list[ImageTag]
    candidate_tags: list[ImageTag]
    processing_time_ms: float
    success: bool
    error: Optional[str] = None


class BatchTagImageResponse(BaseModel):
    """Response from batch image tagging."""
    total_images: int
    successful: int
    failed: int
    results: list[ImageTagResult]
