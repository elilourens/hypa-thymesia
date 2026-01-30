"""Document-related Pydantic schemas."""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class DocumentCreate(BaseModel):
    """Document creation request."""

    group_id: Optional[str] = None
    metadata: Optional[dict] = None


class DocumentResponse(BaseModel):
    """Document response model."""

    id: str
    ragie_document_id: Optional[str] = None
    filename: str
    mime_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    status: str
    chunk_count: Optional[int] = None
    page_count: Optional[int] = None
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class DocumentStatusResponse(BaseModel):
    """Document status response."""

    id: str
    ragie_document_id: Optional[str] = None
    filename: str
    status: str
    chunk_count: Optional[int] = None
    page_count: Optional[int] = None
    updated_at: datetime


class DocumentListResponse(BaseModel):
    """Document list response."""

    items: list[DocumentResponse]
    total: int
    has_more: bool


class DocumentDeleteRequest(BaseModel):
    """Document delete request."""

    pass


class DocumentDeleteResponse(BaseModel):
    """Document delete response."""

    message: str
    document_id: str


class DocumentMetadataUpdate(BaseModel):
    """Update document metadata."""

    metadata: dict
