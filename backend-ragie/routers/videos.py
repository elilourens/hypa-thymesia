"""Video management endpoints."""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, BackgroundTasks
from supabase import Client

from core import get_current_user, AuthUser
from core.deps import get_supabase, get_ragie_service
from core.user_limits import check_user_can_upload
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


def get_video_service(supabase: Client = Depends(get_supabase), ragie_service: RagieService = Depends(get_ragie_service)) -> VideoService:
    """Dependency to get video service."""
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

        # Check user quota
        try:
            check_user_can_upload(supabase, current_user.id)
        except HTTPException:
            raise

        # Upload video
        result = await video_service.upload_video(
            file=file,
            user_id=current_user.id,
            group_id=group_id
        )

        # Queue background task for Ragie processing
        temp_file_path = result.pop("_temp_file_path", None)
        background_tasks.add_task(
            video_service.process_video_with_ragie,
            result["id"],
            current_user.id,
            temp_file_path
        )

        return VideoUploadResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading video: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    """List user's videos with filtering and pagination."""
    try:
        # Query videos
        query = supabase.table("videos").select("*").eq("user_id", current_user.id)

        if group_id:
            query = query.eq("group_id", group_id)

        # Execute query
        response = query.execute()
        all_videos = response.data or []

        # Sort results
        desc = dir == "desc"
        if sort == "created_at":
            all_videos.sort(key=lambda x: x["created_at"], reverse=desc)
        elif sort == "filename":
            all_videos.sort(key=lambda x: x["filename"].lower(), reverse=desc)
        elif sort == "duration_seconds":
            all_videos.sort(key=lambda x: x.get("duration_seconds") or 0, reverse=desc)

        # Get total count
        total_count = len(all_videos)

        # Apply pagination
        offset = (page - 1) * page_size
        paginated_videos = all_videos[offset:offset + page_size]

        # Fetch group names
        group_names = {}
        group_ids = {v.get("group_id") for v in paginated_videos if v.get("group_id")}
        if group_ids:
            groups_response = supabase.table("app_groups").select("group_id, name").eq(
                "user_id", current_user.id
            ).execute()
            group_names = {g["group_id"]: g["name"] for g in (groups_response.data or [])}

        # Format response
        videos = [
            VideoResponse(
                id=v["id"],
                filename=v["filename"],
                storage_path=v["storage_path"],
                file_size_bytes=v["file_size_bytes"],
                duration_seconds=v.get("duration_seconds"),
                fps=v.get("fps"),
                width=v.get("width"),
                height=v.get("height"),
                processing_status=v["processing_status"],
                chunk_count=v.get("chunk_count"),
                group_id=v.get("group_id"),
                group_name=group_names.get(v.get("group_id")) if v.get("group_id") else None,
                created_at=v["created_at"],
                updated_at=v["updated_at"]
            )
            for v in paginated_videos
        ]

        has_more = (offset + page_size) < total_count

        return VideoListResponse(
            items=videos,
            total=total_count,
            has_more=has_more
        )

    except Exception as e:
        logger.error(f"Error listing videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: str,
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase)
):
    """Get a specific video."""
    try:
        response = supabase.table("videos").select("*").eq("id", video_id).eq(
            "user_id", current_user.id
        ).single().execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Video not found")

        v = response.data

        # Fetch group name if applicable
        group_name = None
        if v.get("group_id"):
            group_response = supabase.table("app_groups").select("name").eq(
                "group_id", v["group_id"]
            ).eq("user_id", current_user.id).single().execute()
            if group_response.data:
                group_name = group_response.data.get("name")

        return VideoResponse(
            id=v["id"],
            filename=v["filename"],
            storage_path=v["storage_path"],
            file_size_bytes=v["file_size_bytes"],
            duration_seconds=v.get("duration_seconds"),
            fps=v.get("fps"),
            width=v.get("width"),
            height=v.get("height"),
            processing_status=v["processing_status"],
            chunk_count=v.get("chunk_count"),
            group_id=v.get("group_id"),
            group_name=group_name,
            created_at=v["created_at"],
            updated_at=v["updated_at"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting video: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{video_id}/signed-url", response_model=VideoSignedUrlResponse)
async def get_video_signed_url(
    video_id: str,
    expires_in: int = Query(3600, ge=1, le=604800),
    current_user: AuthUser = Depends(get_current_user),
    video_service: VideoService = Depends(get_video_service)
):
    """Get signed URL for video streaming."""
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

    except Exception as e:
        logger.error(f"Error getting signed URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{video_id}", response_model=VideoDeleteResponse)
async def delete_video(
    video_id: str,
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase)
):
    """Delete a video and its chunks."""
    try:
        # Verify user owns the video
        video_response = supabase.table("videos").select("*").eq("id", video_id).eq(
            "user_id", current_user.id
        ).single().execute()

        if not video_response.data:
            raise HTTPException(status_code=404, detail="Video not found")

        video = video_response.data

        # Delete from Supabase Storage
        try:
            supabase.storage.from_("videos").remove([video["storage_path"]])
        except Exception as e:
            logger.warning(f"Failed to delete video from storage: {e}")
            # Continue with database deletion anyway

        # Delete video record (chunks cascade delete automatically)
        supabase.table("videos").delete().eq("id", video_id).execute()

        return VideoDeleteResponse(
            message="Video deleted successfully",
            video_id=video_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting video: {e}")
        raise HTTPException(status_code=500, detail=str(e))
