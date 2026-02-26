"""Video management endpoints."""

import logging
import asyncio
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from supabase import Client

from core import get_current_user, AuthUser
from core.deps import get_supabase, get_supabase_admin, get_ragie_service
from core.sse import get_sse_manager, SSEManager
from core.user_limits import check_user_can_upload, add_to_user_monthly_throughput, add_to_user_monthly_file_count
from services.video_service import VideoService
from services.ragie_service import RagieService
from schemas.video import (
    VideoUploadResponse,
    VideoResponse,
    VideoListResponse,
    VideoSignedUrlResponse,
    VideoDeleteResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/videos", tags=["videos"])


def _process_video_background(
    video_service: VideoService,
    video_id: str,
    user_id: str,
    temp_file_path: Optional[str],
    thumbnail_path: Optional[str]
):
    """Sync wrapper for async video processing (for background tasks)."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            video_service.process_video_with_ragie(
                video_id=video_id,
                user_id=user_id,
                temp_file_path=temp_file_path,
                thumbnail_path=thumbnail_path
            )
        )
    except Exception as e:
        logger.error(f"Background task failed for video {video_id}: {e}")


def get_video_service(current_user: AuthUser = Depends(get_current_user), supabase: Client = Depends(get_supabase_admin), ragie_service: RagieService = Depends(get_ragie_service)) -> VideoService:
    """Dependency to get video service (uses admin client to bypass RLS for write operations)."""
    return VideoService(supabase, ragie_service)


@router.post("/upload", response_model=VideoUploadResponse)
async def upload_video(
    file: UploadFile = File(...),
    group_id: Optional[str] = Query(None),
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
    video_service: VideoService = Depends(get_video_service),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Upload a video to Supabase Storage."""
    try:
        # Validate file is MP4
        if not file.filename.endswith(".mp4"):
            raise HTTPException(status_code=400, detail="Only MP4 files are supported")

        # Get file size before upload
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        # Check user quota with file size
        try:
            check_user_can_upload(supabase, current_user.id, file_size_bytes=file_size)
        except HTTPException:
            raise

        # Upload video
        result = await video_service.upload_video(
            file=file,
            user_id=current_user.id,
            group_id=group_id
        )

        # Track upload throughput and file count
        add_to_user_monthly_throughput(supabase, current_user.id, file_size)
        add_to_user_monthly_file_count(supabase, current_user.id)

        # Queue background task for Ragie processing
        temp_file_path = result.pop("_temp_file_path", None)
        thumbnail_path = result.pop("_thumbnail_path", None)
        logger.info(f"Queueing background task for video {result['id']}")
        background_tasks.add_task(
            _process_video_background,
            video_service,
            result["id"],
            current_user.id,
            temp_file_path,
            thumbnail_path
        )

        # Map status -> processing_status for response
        return VideoUploadResponse(
            id=result["id"],
            filename=result["filename"],
            storage_path=result["storage_path"],
            file_size_bytes=result["file_size_bytes"],
            duration_seconds=result.get("duration_seconds"),
            processing_status=result["processing_status"],  # From ragie_documents.status
            created_at=result["created_at"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading video: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload video")


@router.get("/list", response_model=VideoListResponse)
async def list_videos(
    group_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("created_at", regex="^(created_at|filename|duration_seconds)$"),
    dir: str = Query("desc", regex="^(asc|desc)$"),
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase)
):
    """List user's videos (from ragie_documents) with filtering and pagination."""
    try:
        # Query ragie_documents with database-level pagination
        query = supabase.table("ragie_documents").select("*").eq("user_id", current_user.id)

        if group_id:
            query = query.eq("group_id", group_id)

        # Apply sorting at database level
        desc = dir == "desc"
        if sort == "created_at":
            query = query.order("created_at", desc=desc)
        elif sort == "filename":
            query = query.order("filename", desc=desc)
        elif sort == "duration_seconds":
            query = query.order("duration_seconds", desc=desc)

        # Apply pagination at database level
        offset = (page - 1) * page_size
        response = query.range(offset, offset + page_size - 1).execute()
        paginated_docs = response.data or []

        # Get total count (all matching videos, not just this page)
        count_query = supabase.table("ragie_documents").select("*").eq("user_id", current_user.id)
        if group_id:
            count_query = count_query.eq("group_id", group_id)
        count_response = count_query.execute()
        total_count = len(count_response.data or [])

        # Fetch group names
        group_names = {}
        group_ids = {d.get("group_id") for d in paginated_docs if d.get("group_id")}
        if group_ids:
            groups_response = supabase.table("app_groups").select("group_id, name").eq(
                "user_id", current_user.id
            ).execute()
            group_names = {g["group_id"]: g["name"] for g in (groups_response.data or [])}

        # Format response
        videos = [
            VideoResponse(
                id=d["id"],
                filename=d["filename"],
                storage_path=d["storage_path"],
                file_size_bytes=d["file_size_bytes"],
                duration_seconds=d.get("duration_seconds"),
                fps=d.get("fps"),
                width=d.get("width"),
                height=d.get("height"),
                processing_status=d["status"],
                chunk_count=d.get("chunk_count"),
                group_id=d.get("group_id"),
                group_name=group_names.get(d.get("group_id")) if d.get("group_id") else None,
                created_at=d["created_at"],
                updated_at=d["updated_at"],
                thumbnail_url=None
            )
            for d in paginated_docs
        ]

        has_more = (offset + page_size) < total_count

        return VideoListResponse(
            items=videos,
            total=total_count,
            has_more=has_more
        )

    except Exception as e:
        logger.error(f"Error listing videos: {e}")
        raise HTTPException(status_code=500, detail="Failed to list videos")


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: str,
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase)
):
    """Get a specific video (from ragie_documents)."""
    try:
        response = supabase.table("ragie_documents").select("*").eq("id", video_id).eq(
            "user_id", current_user.id
        ).single().execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Video not found")

        doc = response.data

        # Fetch group name if applicable
        group_name = None
        if doc.get("group_id"):
            group_response = supabase.table("app_groups").select("name").eq(
                "group_id", doc["group_id"]
            ).eq("user_id", current_user.id).single().execute()
            if group_response.data:
                group_name = group_response.data.get("name")

        return VideoResponse(
            id=doc["id"],
            filename=doc["filename"],
            storage_path=doc["storage_path"],
            file_size_bytes=doc["file_size_bytes"],
            duration_seconds=doc.get("duration_seconds"),
            fps=doc.get("fps"),
            width=doc.get("width"),
            height=doc.get("height"),
            processing_status=doc["status"],
            chunk_count=doc.get("chunk_count"),
            group_id=doc.get("group_id"),
            group_name=group_name,
            thumbnail_url=None,
            created_at=doc["created_at"],
            updated_at=doc["updated_at"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting video: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve video")


@router.get("/{video_id}/chunks", response_model=list)
async def get_video_chunks(
    video_id: str,
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
    video_service: VideoService = Depends(get_video_service)
):
    """Get video chunks with signed thumbnail URLs (from ragie_documents)."""
    try:
        # Verify user owns the document
        doc_response = supabase.table("ragie_documents").select("id").eq("id", video_id).eq(
            "user_id", current_user.id
        ).single().execute()

        if not doc_response.data:
            raise HTTPException(status_code=404, detail="Video not found")

        # Get chunks by ragie_document_id
        chunks_response = supabase.table("video_chunks").select("*").eq(
            "ragie_document_id", video_id
        ).order("chunk_index", desc=False).execute()

        chunks = chunks_response.data or []

        # Generate signed URLs for thumbnails
        for chunk in chunks:
            if chunk.get("thumbnail_url"):
                signed_url = video_service.get_signed_thumbnail_url(
                    chunk["thumbnail_url"],
                    expires_in=3600
                )
                chunk["thumbnail_url"] = signed_url

        return chunks

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting video chunks: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve video chunks")


@router.get("/{video_id}/signed-url", response_model=VideoSignedUrlResponse)
async def get_video_signed_url(
    video_id: str,
    expires_in: int = Query(3600, ge=1, le=604800),
    current_user: AuthUser = Depends(get_current_user),
    video_service: VideoService = Depends(get_video_service)
):
    """Get signed URL for video streaming (from ragie_documents)."""
    try:
        url = await video_service.get_signed_video_url(
            video_id=video_id,
            user_id=current_user.id,
            expires_in=expires_in
        )

        return VideoSignedUrlResponse(
            url=url,
            expires_in=expires_in
        )

    except HTTPException:
        raise
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Video not found")
        logger.error(f"Error getting signed URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to get signed URL")


@router.delete("/{video_id}", response_model=VideoDeleteResponse)
async def delete_video(
    video_id: str,
    current_user: AuthUser = Depends(get_current_user),
    video_service: VideoService = Depends(get_video_service)
):
    """Delete a video (ragie_documents record) and all associated files."""
    try:
        await video_service.delete_document(video_id, current_user.id)

        return VideoDeleteResponse(
            message="Video deleted successfully",
            video_id=video_id
        )

    except HTTPException:
        raise
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Video not found")
        logger.error(f"Error deleting video: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete video")


@router.get("/{video_id}/updates")
async def video_status_stream(
    video_id: str,
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
    sse_manager: SSEManager = Depends(get_sse_manager)
):
    """Stream video processing status updates via Server-Sent Events (SSE).

    This endpoint allows the frontend to receive real-time updates when
    the video processing status changes, eliminating the need for polling.
    """
    # Verify user owns the video
    try:
        response = supabase.table("ragie_documents").select("id").eq("id", video_id).eq(
            "user_id", current_user.id
        ).single().execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Video not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying video ownership: {e}")
        raise HTTPException(status_code=500, detail="Failed to verify video")

    # Generate unique client ID
    client_id = str(uuid.uuid4())
    client = sse_manager.add_client(video_id, client_id)

    async def event_generator():
        """Generate SSE events for status updates."""
        try:
            # Send initial connection message
            yield f"data: {{'event': 'connected', 'video_id': '{video_id}'}}\n\n"

            # Stream messages from the queue
            while client.connected:
                try:
                    # Wait for a message with 30 second timeout
                    # (clients need to receive something periodically to detect disconnection)
                    data = await asyncio.wait_for(client.queue.get(), timeout=30.0)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    # Send a heartbeat to keep connection alive
                    yield f": heartbeat\n\n"
                except asyncio.CancelledError:
                    break

        finally:
            await client.disconnect()
            sse_manager.remove_client(video_id, client_id)
            logger.info(f"SSE stream ended for video {video_id}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )
