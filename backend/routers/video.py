"""
Video ingestion and query router.
Proxies upload requests to the hypa-thymesia-video-query service.
Handles video queries directly using local embedders and Pinecone.
"""
import logging
import httpx
import os
from typing import Optional, List, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, Form
from pydantic import BaseModel
from core.config import get_settings
from core.deps import get_supabase
from core.security import get_current_user, AuthUser
from core.user_limits import check_user_can_upload, ensure_user_settings_exist
from embed.video_embeddings import get_clip_embedder, get_transcript_embedder
from data_upload.pinecone_services import query_vectors

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
        # Initialize embedders (singletons, lazy loaded)
        clip_embedder = get_clip_embedder()
        transcript_embedder = get_transcript_embedder()

        # Prepare metadata filter
        meta_filter = None
        if group_id:
            meta_filter = {"group_id": {"$eq": group_id}}

        matches = []

        if route == "video_frames":
            # Query video frames using CLIP text embedding
            logger.info(f"Querying video frames for user {user_id}: {query_text[:50]}...")
            query_embedding = clip_embedder.embed_text(query_text)

            result = query_vectors(
                vector=query_embedding.tolist(),
                modality="video_frame",
                top_k=top_k * 3,  # Fetch more for diversity
                namespace=user_id,
                metadata_filter=meta_filter,
                include_metadata=True,
            )

            # Format and diversify results
            matches = _format_video_results(result, "video_frame")
            matches = _diversify_frame_results(matches, top_k)

        elif route == "video_transcript":
            # Query video transcripts using transcript embedding
            logger.info(f"Querying video transcripts for user {user_id}: {query_text[:50]}...")
            query_embedding = transcript_embedder.embed_text(query_text)

            result = query_vectors(
                vector=query_embedding.tolist(),
                modality="video_transcript",
                top_k=top_k * 3,  # Fetch more for diversity
                namespace=user_id,
                metadata_filter=meta_filter,
                include_metadata=True,
            )

            # Format and diversify results
            matches = _format_video_results(result, "video_transcript")
            matches = _diversify_transcript_results(matches, top_k)

        elif route == "video_combined":
            # Query both frames and transcripts
            logger.info(f"Querying video frames+transcripts for user {user_id}: {query_text[:50]}...")

            frame_embedding = clip_embedder.embed_text(query_text)
            transcript_embedding = transcript_embedder.embed_text(query_text)

            frame_result = query_vectors(
                vector=frame_embedding.tolist(),
                modality="video_frame",
                top_k=top_k * 3,
                namespace=user_id,
                metadata_filter=meta_filter,
                include_metadata=True,
            )

            transcript_result = query_vectors(
                vector=transcript_embedding.tolist(),
                modality="video_transcript",
                top_k=top_k * 3,
                namespace=user_id,
                metadata_filter=meta_filter,
                include_metadata=True,
            )

            # Format and diversify each type
            frame_matches = _format_video_results(frame_result, "video_frame")
            transcript_matches = _format_video_results(transcript_result, "video_transcript")

            frame_matches = _diversify_frame_results(frame_matches, top_k)
            transcript_matches = _diversify_transcript_results(transcript_matches, top_k)

            # Combine both result types
            matches = frame_matches + transcript_matches

        logger.info(f"Video query completed: {len(matches)} results for user {user_id}")

        return {
            "matches": matches,
            "top_k": top_k,
            "route": route,
            "namespace": user_id,
        }

    except Exception as e:
        logger.error(f"Video query failed for user {user_id}: {e}", exc_info=True)
        raise HTTPException(500, detail=f"Video query failed: {str(e)}")


# Helper functions for video query processing

def _format_video_results(result, source_type: str) -> List[Dict[str, Any]]:
    """Format Pinecone results and enrich metadata for frontend."""
    formatted = []

    for match in result.matches:
        metadata = dict(match.metadata or {})

        # Add source field for frontend
        metadata["source"] = source_type

        # Add title field (use video_filename or default)
        if "video_filename" in metadata and "title" not in metadata:
            metadata["title"] = metadata["video_filename"]

        formatted.append({
            "id": match.id,
            "score": match.score,
            "metadata": metadata,
        })

    return formatted


def _diversify_frame_results(results: List[Dict[str, Any]], n_results: int) -> List[Dict[str, Any]]:
    """Apply diversity to video frame results based on scene_id or timestamp."""
    if len(results) <= n_results:
        return results

    selected = []
    remaining = results.copy()
    selected_scenes = set()

    # Always select the best match first
    first_result = remaining.pop(0)
    selected.append(first_result)
    if "scene_id" in first_result["metadata"]:
        selected_scenes.add(first_result["metadata"]["scene_id"])

    has_scene_ids = "scene_id" in first_result["metadata"]

    # Greedily select remaining results
    while len(selected) < n_results and remaining:
        best_score = -float("inf")
        best_idx = 0

        for idx, candidate in enumerate(remaining):
            if has_scene_ids:
                # Scene-based diversity
                candidate_scene = candidate["metadata"].get("scene_id")
                diversity_score = 1.0 if candidate_scene not in selected_scenes else 0.0
            else:
                # Time-based diversity
                min_time_diff = float("inf")
                candidate_time = candidate["metadata"]["timestamp"]

                for selected_result in selected:
                    selected_time = selected_result["metadata"]["timestamp"]
                    time_diff = abs(candidate_time - selected_time)
                    min_time_diff = min(min_time_diff, time_diff)

                diversity_score = min(min_time_diff / 10.0, 1.0)

            # Combined score (50% relevance, 50% diversity)
            combined_score = 0.5 * candidate["score"] + 0.5 * diversity_score

            if combined_score > best_score:
                best_score = combined_score
                best_idx = idx

        selected_result = remaining.pop(best_idx)
        selected.append(selected_result)

        if has_scene_ids and "scene_id" in selected_result["metadata"]:
            selected_scenes.add(selected_result["metadata"]["scene_id"])

    return selected


def _diversify_transcript_results(results: List[Dict[str, Any]], n_results: int) -> List[Dict[str, Any]]:
    """Apply temporal diversity to video transcript results."""
    if len(results) <= n_results:
        return results

    selected = []
    remaining = results.copy()

    # Always select the best match first
    selected.append(remaining.pop(0))

    # Greedily select remaining results
    while len(selected) < n_results and remaining:
        best_score = -float("inf")
        best_idx = 0

        for idx, candidate in enumerate(remaining):
            # Calculate temporal diversity
            min_time_diff = float("inf")
            candidate_start = float(candidate["metadata"]["start_time"])

            for selected_result in selected:
                selected_start = float(selected_result["metadata"]["start_time"])
                time_diff = abs(candidate_start - selected_start)
                min_time_diff = min(min_time_diff, time_diff)

            # Normalize temporal diversity (20s = full diversity)
            diversity_score = min(min_time_diff / 20.0, 1.0)

            # Combined score (50% relevance, 50% diversity)
            combined_score = 0.5 * candidate["score"] + 0.5 * diversity_score

            if combined_score > best_score:
                best_score = combined_score
                best_idx = idx

        selected.append(remaining.pop(best_idx))

    return selected
