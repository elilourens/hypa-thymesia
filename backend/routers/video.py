"""
Video ingestion and query router.
Proxies requests to the hypa-thymesia-video-query service.
"""
import logging
import httpx
import os
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, Form
from pydantic import BaseModel
from core.config import get_settings
from core.deps import get_supabase
from core.security import get_current_user, AuthUser
from core.user_limits import check_user_can_upload, ensure_user_settings_exist

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["video"])

# Video service URL - configurable via environment variable
VIDEO_SERVICE_URL = os.getenv("VIDEO_SERVICE_URL", "http://localhost:8001")


async def process_video_background(
    file_content: bytes,
    filename: str,
    mime_type: str,
    user_id: str,
    doc_id: str,
    group_id: Optional[str],
):
    """
    Background task to process video ingestion.
    Sends video to the video-query service for processing.
    """
    from core.deps import get_supabase

    supabase = get_supabase()

    try:
        # Update status to processing
        supabase.table("app_doc_meta").update({
            "processing_status": "processing"
        }).eq("doc_id", doc_id).execute()

        logger.info(f"Background video processing started: {filename} (doc_id={doc_id})")

        # Send video to video-query service
        async with httpx.AsyncClient(timeout=600.0) as client:  # 10 minute timeout
            files = {"file": (filename, file_content, mime_type)}
            data = {
                "user_id": user_id,
                "video_id": doc_id,
                "group_id": group_id or "",
            }

            response = await client.post(
                f"{VIDEO_SERVICE_URL}/api/v1/video/upload",
                files=files,
                data=data,
            )
            response.raise_for_status()
            result = response.json()

        # Update status to completed
        supabase.table("app_doc_meta").update({
            "processing_status": "completed",
            "text_chunks_count": result.get("transcript_chunks_count", 0),
            "images_count": result.get("frame_count", 0),
        }).eq("doc_id", doc_id).execute()

        logger.info(f"Background video processing completed: {filename} (doc_id={doc_id})")

    except httpx.HTTPStatusError as e:
        logger.error(f"Video service HTTP error: {e.response.status_code} - {e.response.text}")

        supabase.table("app_doc_meta").update({
            "processing_status": "failed",
            "error_message": f"Video service error: {e.response.status_code}"
        }).eq("doc_id", doc_id).execute()

    except Exception as e:
        logger.error(f"Background video processing failed for {filename} (doc_id={doc_id}): {e}", exc_info=True)

        try:
            supabase.table("app_doc_meta").update({
                "processing_status": "failed",
                "error_message": str(e)[:500]
            }).eq("doc_id", doc_id).execute()
        except Exception as update_error:
            logger.error(f"Failed to update error status: {update_error}")


@router.post("/upload-video")
async def ingest_video(
    file: UploadFile = File(...),
    group_id: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = None,
    auth: AuthUser = Depends(get_current_user),
    supabase = Depends(get_supabase),
    settings = Depends(get_settings),
):
    """
    Upload and process a video file.
    Returns immediately with doc_id and status='queued'.
    """
    user_id = auth.id

    # Ensure user settings exist
    ensure_user_settings_exist(supabase, user_id)

    # Check if user can upload (raises HTTPException if limit reached)
    check_user_can_upload(supabase, user_id)

    # Validate file type
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("mp4", "avi", "mov", "mkv", "webm"):
        raise HTTPException(400, detail="Invalid video format. Supported: .mp4, .avi, .mov, .mkv, .webm")

    content = await file.read()
    logger.debug(f"Video upload started: {file.filename}, size: {len(content)} bytes")

    # Generate doc_id upfront
    doc_id = str(uuid4())

    # Create doc_meta record with 'queued' status
    try:
        from utils.db_helpers import ensure_doc_meta
        ensure_doc_meta(supabase, user_id=user_id, doc_id=doc_id, group_id=group_id)

        supabase.table("app_doc_meta").update({
            "processing_status": "queued",
            "filename": file.filename,
            "mime_type": file.content_type,
            "modality": "video",  # Mark as video
        }).eq("doc_id", doc_id).execute()

        logger.info(f"Created video doc_meta record: doc_id={doc_id}, status=queued")
    except Exception as e:
        logger.error(f"Error creating doc_meta: {e}", exc_info=True)
        raise HTTPException(500, detail="Failed to create document record")

    # Queue background processing
    if background_tasks:
        background_tasks.add_task(
            process_video_background,
            file_content=content,
            filename=file.filename,
            mime_type=file.content_type,
            user_id=user_id,
            doc_id=doc_id,
            group_id=group_id,
        )
        logger.info(f"Queued background video processing: {file.filename} (doc_id={doc_id})")
    else:
        logger.warning("BackgroundTasks not available, processing video synchronously")
        await process_video_background(
            file_content=content,
            filename=file.filename,
            mime_type=file.content_type,
            user_id=user_id,
            doc_id=doc_id,
            group_id=group_id,
        )

    return {
        "doc_id": doc_id,
        "status": "queued",
        "message": "Video uploaded successfully. Processing in background.",
        "filename": file.filename,
    }


class VideoQueryRequest(BaseModel):
    """Request model for video query."""
    query_text: str
    route: str = "video_frames"
    top_k: int = 10
    group_id: Optional[str] = None


@router.post("/query-video")
async def query_video(
    request: VideoQueryRequest,
    auth: AuthUser = Depends(get_current_user),
):
    """
    Query video content by text.
    Routes to video frames, transcripts, or combined search.
    """
    user_id = auth.id

    query_text = request.query_text
    route = request.route
    top_k = request.top_k
    group_id = request.group_id

    if route not in ("video_frames", "video_transcript", "video_combined"):
        raise HTTPException(
            422,
            detail="route must be 'video_frames', 'video_transcript', or 'video_combined'"
        )

    try:
        # Proxy request to video-query service
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{VIDEO_SERVICE_URL}/api/v1/video/query",
                json={
                    "user_id": user_id,
                    "query_text": query_text,
                    "route": route,
                    "top_k": top_k,
                    "group_id": group_id,
                }
            )
            response.raise_for_status()
            result = response.json()

            # Transform response to match frontend expectations
            # Video service returns {"results": [...]}, frontend expects {"matches": [...]}
            matches = result.get("results", [])

            # Handle combined route: flatten dict of {frames: [...], transcripts: [...]} into single list
            if isinstance(matches, dict) and ("frames" in matches or "transcripts" in matches):
                flattened = []

                # Add frames
                if "frames" in matches and isinstance(matches["frames"], list):
                    for match in matches["frames"]:
                        if isinstance(match, dict) and "metadata" in match:
                            meta = match["metadata"]
                            if "video_filename" in meta and "title" not in meta:
                                meta["title"] = meta["video_filename"]
                            if "source" not in meta:
                                meta["source"] = "video_frame"
                        flattened.append(match)

                # Add transcripts
                if "transcripts" in matches and isinstance(matches["transcripts"], list):
                    for match in matches["transcripts"]:
                        if isinstance(match, dict) and "metadata" in match:
                            meta = match["metadata"]
                            if "video_filename" in meta and "title" not in meta:
                                meta["title"] = meta["video_filename"]
                            if "source" not in meta:
                                meta["source"] = "video_transcript"
                        flattened.append(match)

                matches = flattened

            # Enrich metadata for single-route responses (already a list)
            elif isinstance(matches, list):
                for match in matches:
                    if isinstance(match, dict) and "metadata" in match:
                        meta = match["metadata"]
                        # Add title field (use video_filename or default)
                        if "video_filename" in meta and "title" not in meta:
                            meta["title"] = meta["video_filename"]
                        # Add source field (frontend checks for 'source', not 'modality')
                        if "source" not in meta:
                            if "timestamp" in meta or "frame_index" in meta:
                                meta["source"] = "video_frame"
                            elif "text" in meta or "start_time" in meta:
                                meta["source"] = "video_transcript"

            return {
                "matches": matches,
                "top_k": top_k,
                "route": route,
                "namespace": user_id,
            }

    except httpx.HTTPStatusError as e:
        logger.error(f"Video query service error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Video query service error: {e.response.text}"
        )
    except Exception as e:
        logger.error(f"Video query failed: {e}", exc_info=True)
        raise HTTPException(500, detail=f"Video query failed: {str(e)}")
