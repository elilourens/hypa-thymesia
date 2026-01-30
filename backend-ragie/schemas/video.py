"""Video-related response schemas."""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class VideoUploadResponse(BaseModel):
    """Response for uploading a video."""
    id: str
    filename: str
    storage_path: str
    file_size_bytes: int
    duration_seconds: Optional[float] = None
    processing_status: str
    created_at: datetime

    class Config:
        from_attributes = True


class VideoChunkResponse(BaseModel):
    """Response for a video chunk from Ragie processing."""
    id: str
    video_id: str
    chunk_index: Optional[int] = None
    start_time: float
    end_time: float
    audio_transcript: Optional[str] = None
    video_description: Optional[str] = None
    storage_url: Optional[str] = None

    class Config:
        from_attributes = True


class VideoResponse(BaseModel):
    """Full video details."""
    id: str
    filename: str
    storage_path: str
    file_size_bytes: int
    duration_seconds: Optional[float] = None
    fps: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    processing_status: str
    chunk_count: Optional[int] = None
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VideoListResponse(BaseModel):
    """Paginated list of videos."""
    items: List[VideoResponse]
    total: int
    has_more: bool


class VideoSignedUrlResponse(BaseModel):
    """Response with signed URL for video streaming."""
    url: str
    expires_in: int


class VideoDeleteResponse(BaseModel):
    """Response for video deletion."""
    message: str
    video_id: str
