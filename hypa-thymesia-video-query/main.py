"""
FastAPI application for video ingestion and query service.
This microservice handles video processing using CLIP and Whisper,
storing embeddings in Pinecone and metadata in Supabase.
"""
import os
import logging
import tempfile
from pathlib import Path
from typing import Optional, Union
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from src.embeddings.clip_embedder import CLIPEmbedder
from src.embeddings.transcript_embedder import TranscriptEmbedder
from src.video.processor import VideoProcessor
from src.audio.audio_processor import AudioProcessor
from src.storage.unified_database import VideoFrameDatabase, TranscriptDatabase
from src.storage import supabase_service as sb
from src.storage import pinecone_service as pc

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Hypa Thymesia Video Query Service",
    description="Video embedding and querying microservice using CLIP and Pinecone",
    version="0.1.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global model instances (lazy loaded)
_clip_embedder = None
_transcript_embedder = None
_video_processor = None
_audio_processor = None


def get_clip_embedder() -> CLIPEmbedder:
    """Get or initialize CLIP embedder (singleton)."""
    global _clip_embedder
    if _clip_embedder is None:
        logger.info("Initializing CLIP embedder...")
        _clip_embedder = CLIPEmbedder()
    return _clip_embedder


def get_transcript_embedder() -> TranscriptEmbedder:
    """Get or initialize transcript embedder (singleton)."""
    global _transcript_embedder
    if _transcript_embedder is None:
        logger.info("Initializing transcript embedder...")
        _transcript_embedder = TranscriptEmbedder()
    return _transcript_embedder


def get_video_processor() -> VideoProcessor:
    """Get or initialize video processor (singleton)."""
    global _video_processor
    if _video_processor is None:
        logger.info("Initializing video processor...")
        _video_processor = VideoProcessor()
    return _video_processor


def get_audio_processor() -> AudioProcessor:
    """Get or initialize audio processor (singleton)."""
    global _audio_processor
    if _audio_processor is None:
        whisper_model = os.getenv("WHISPER_MODEL", "base")
        logger.info(f"Initializing audio processor with Whisper model: {whisper_model}")
        _audio_processor = AudioProcessor(whisper_model)
    return _audio_processor


class VideoUploadRequest(BaseModel):
    """Request model for video upload (from form data)."""
    user_id: str
    video_id: str
    group_id: Optional[str] = None


class VideoQueryRequest(BaseModel):
    """Request model for video query."""
    user_id: str
    query_text: str
    route: str = "video_frames"  # "video_frames", "video_transcript", or "video_combined"
    top_k: int = 10
    group_id: Optional[str] = None


class VideoUploadResponse(BaseModel):
    """Response model for video upload."""
    video_id: str
    frame_count: int
    transcript_chunks_count: int
    message: str


class VideoQueryResponse(BaseModel):
    """Response model for video query."""
    results: Union[list, dict]  # list for single route, dict for combined route


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "service": "hypa-thymesia-video-query",
        "status": "running",
        "version": "0.1.0"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/api/v1/video/upload", response_model=VideoUploadResponse)
async def upload_video(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    video_id: str = Form(...),
    group_id: Optional[str] = Form(None),
):
    """
    Upload and process a video file.

    - Extracts frames and generates CLIP embeddings
    - Transcribes audio using Whisper
    - Stores embeddings in Pinecone
    - Stores video file in Supabase storage

    Args:
        file: Video file to process
        user_id: User ID for namespace isolation
        video_id: Unique video identifier (doc_id from main backend)
        group_id: Optional group ID for filtering

    Returns:
        VideoUploadResponse with frame count and transcript count
    """
    logger.info(f"Received video upload: video_id={video_id}, user_id={user_id}, filename={file.filename}")

    # Validate file type
    if not file.filename:
        raise HTTPException(400, detail="No filename provided")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("mp4", "avi", "mov", "mkv", "webm"):
        raise HTTPException(400, detail=f"Invalid video format: .{ext}. Supported: .mp4, .avi, .mov, .mkv, .webm")

    # Read file content
    content = await file.read()

    # Upload video file to Supabase storage FIRST (before processing)
    logger.info("Uploading video file to Supabase storage...")
    storage_path = None
    try:
        storage_path = sb.upload_video_to_bucket(
            file_content=content,
            filename=file.filename,
            user_id=user_id,
            mime_type=file.content_type,
        )
        if not storage_path:
            raise HTTPException(500, detail="Failed to upload video to storage")

        logger.info(f"Video uploaded to storage: {storage_path}")

        # Update app_doc_meta with storage_path
        sb.supabase.table("app_doc_meta").update({
            "storage_path": storage_path,
        }).eq("doc_id", video_id).eq("user_id", user_id).execute()

        # Create chunk entry for the video file itself
        video_chunk_id = str(uuid4())
        sb.supabase.table("app_chunks").insert({
            "chunk_id": video_chunk_id,
            "doc_id": video_id,
            "chunk_index": 1,
            "modality": "video",
            "storage_path": storage_path,
            "bucket": sb.VIDEO_BUCKET,
            "mime_type": file.content_type,
            "user_id": user_id,
            "size_bytes": len(content),
        }).execute()
        logger.info(f"Created video chunk entry: {video_chunk_id}")

    except Exception as e:
        logger.error(f"Failed to upload video to storage: {e}", exc_info=True)
        raise HTTPException(500, detail=f"Failed to upload video to storage: {str(e)}")

    # Create temporary file for video processing
    temp_video_path = None
    try:
        # Save uploaded file to temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as temp_file:
            temp_file.write(content)
            temp_video_path = temp_file.name

        logger.info(f"Saved video to temporary file: {temp_video_path}")

        # Initialize components
        clip_embedder = get_clip_embedder()
        transcript_embedder = get_transcript_embedder()
        video_processor = get_video_processor()
        audio_processor = get_audio_processor()

        # Initialize databases
        frame_db = VideoFrameDatabase(user_id=user_id)
        transcript_db = TranscriptDatabase(user_id=user_id)

        # Process video frames
        logger.info("Extracting frames from video...")
        frame_interval = float(os.getenv("FRAME_INTERVAL", "1.5"))
        frames = video_processor.extract_frames(
            video_path=temp_video_path,
            frame_interval=frame_interval,
            skip_solid_frames=True,
            save_frames_to_disk=False,  # Don't save frames locally
        )

        if not frames:
            raise HTTPException(400, detail="No frames extracted from video")

        logger.info(f"Extracted {len(frames)} frames")

        # Detect scene changes
        detect_scenes = os.getenv("DETECT_SCENES", "true").lower() == "true"
        scene_ids = None
        if detect_scenes:
            scene_threshold = float(os.getenv("SCENE_THRESHOLD", "30.0"))
            logger.info("Detecting scene changes...")
            scene_ids = video_processor.detect_scene_changes(frames, scene_threshold)

        # Upload frames to Supabase storage and generate embeddings
        logger.info("Uploading frames to Supabase and generating embeddings...")
        embeddings = []
        metadatas = []
        ids = []

        # Prepare all frame data first
        frame_upload_tasks = []
        for idx, (frame, timestamp) in enumerate(frames):
            # Generate embedding
            embedding = clip_embedder.embed_image(frame)
            embeddings.append(embedding.tolist())

            # Prepare frame upload task
            frame_filename = f"{video_id}_frame_{idx}.jpg"
            frame_upload_tasks.append({
                "frame": frame,
                "user_id": user_id,
                "video_id": video_id,
                "frame_filename": frame_filename,
                "idx": idx,
                "timestamp": float(timestamp),  # Convert numpy float64 to Python float
            })

        # Batch upload frames to Supabase with controlled concurrency and retry logic
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time
        import random

        # Configuration - VERY conservative settings to avoid connection issues
        BATCH_SIZE = 5  # Process only 5 frames at a time
        MAX_WORKERS = 1  # Sequential uploads only (no parallel uploads)
        BATCH_DELAY = 1.0  # 1 second delay between batches
        MAX_RETRIES = 5  # Increased retries
        DELAY_BETWEEN_UPLOADS = 0.3  # 300ms delay between each upload

        def upload_frame_with_retry(task, max_retries=MAX_RETRIES):
            """Upload a frame with exponential backoff + jitter retry logic."""
            for attempt in range(max_retries):
                try:
                    result = sb.upload_frame(
                        frame=task["frame"],
                        user_id=task["user_id"],
                        video_id=task["video_id"],
                        frame_filename=task["frame_filename"]
                    )
                    # Delay after successful upload to avoid overwhelming connection pool
                    time.sleep(DELAY_BETWEEN_UPLOADS)
                    return result
                except Exception as e:
                    if attempt == max_retries - 1:
                        # Last attempt failed - log but don't crash, mark as failed
                        logger.error(f"Upload failed for frame {task['idx']} after {max_retries} attempts: {e}")
                        # Return None instead of raising to allow processing to continue
                        return None
                    # Exponential backoff with jitter: 1-2s, 2-4s, 4-8s, etc.
                    base_wait = 2 ** attempt
                    jitter = random.uniform(0, base_wait)
                    wait_time = base_wait + jitter
                    logger.warning(f"Upload failed for frame {task['idx']}, retrying in {wait_time:.1f}s... (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(wait_time)

        logger.info(f"Uploading {len(frame_upload_tasks)} frames to Supabase sequentially (batch_size={BATCH_SIZE}, delay={DELAY_BETWEEN_UPLOADS}s)...")
        storage_paths = [None] * len(frame_upload_tasks)
        failed_frames = []

        # Process frames in small batches sequentially
        for batch_num in range(0, len(frame_upload_tasks), BATCH_SIZE):
            batch_end = min(batch_num + BATCH_SIZE, len(frame_upload_tasks))
            batch_tasks = frame_upload_tasks[batch_num:batch_end]

            logger.info(f"Processing batch {batch_num // BATCH_SIZE + 1}/{(len(frame_upload_tasks) + BATCH_SIZE - 1) // BATCH_SIZE} ({len(batch_tasks)} frames)")

            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future_to_idx = {
                    executor.submit(upload_frame_with_retry, task): task["idx"]
                    for task in batch_tasks
                }

                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        result = future.result()
                        if result is None:
                            failed_frames.append(idx)
                            logger.warning(f"Frame {idx} failed to upload, will skip in embeddings")
                        else:
                            storage_paths[idx] = result
                    except Exception as e:
                        logger.error(f"Unexpected error uploading frame {idx}: {e}")
                        failed_frames.append(idx)

            # Delay between batches to let connection pool recover
            if batch_end < len(frame_upload_tasks):
                time.sleep(BATCH_DELAY)

        # Log upload summary
        successful_uploads = sum(1 for p in storage_paths if p is not None)
        logger.info(f"Upload complete: {successful_uploads}/{len(frame_upload_tasks)} frames uploaded successfully")
        if failed_frames:
            logger.warning(f"Failed frames: {failed_frames}")

        # Prepare metadata and create chunk entries for frames after uploads complete (skip failed frames)
        frame_chunk_rows = []
        for task, storage_path in zip(frame_upload_tasks, storage_paths):
            # Skip frames that failed to upload
            if storage_path is None:
                continue

            idx = task["idx"]
            timestamp = task["timestamp"]

            metadata = {
                "video_id": video_id,
                "timestamp": timestamp,
                "frame_index": idx,
                "storage_path": storage_path,
                "bucket": "video-frames",
                "video_filename": file.filename,
            }

            if scene_ids is not None:
                metadata["scene_id"] = int(scene_ids[idx])  # Convert numpy int to Python int

            if group_id:
                metadata["group_id"] = group_id

            metadatas.append(metadata)
            ids.append(f"{video_id}:frame_{idx}")

            # Prepare chunk row for this frame
            frame_chunk_rows.append({
                "chunk_id": str(uuid4()),
                "doc_id": video_id,
                "chunk_index": idx + 2,  # Start at 2 (1 is the video file itself)
                "modality": "video_frame",
                "storage_path": storage_path,
                "bucket": "video-frames",
                "mime_type": "image/jpeg",
                "user_id": user_id,
            })

        # Batch insert frame chunks into app_chunks
        if frame_chunk_rows:
            logger.info(f"Creating {len(frame_chunk_rows)} frame chunk entries in app_chunks...")
            sb.supabase.table("app_chunks").insert(frame_chunk_rows).execute()
            logger.info(f"Successfully created {len(frame_chunk_rows)} frame chunk entries")

        # Filter embeddings to match successful uploads only
        if failed_frames:
            logger.info(f"Filtering embeddings: keeping {len(metadatas)} out of {len(embeddings)} embeddings")
            embeddings = [emb for i, emb in enumerate(embeddings) if i not in failed_frames]

        # Add frames to database
        frame_db.add_frames(embeddings, metadatas, ids)
        logger.info(f"Successfully indexed {len(frames)} frames")

        # Process transcript
        logger.info("Transcribing audio...")
        transcript_data = audio_processor.transcribe(temp_video_path)

        chunk_duration = float(os.getenv("CHUNK_DURATION", "20.0"))
        chunks = audio_processor.chunk_transcript(transcript_data, chunk_duration)

        transcript_count = 0
        if chunks:
            logger.info(f"Generating embeddings for {len(chunks)} transcript chunks...")

            # Extract texts for batch embedding
            texts = [chunk["text"] for chunk in chunks]

            # Generate embeddings in batch
            transcript_embeddings = transcript_embedder.embed_batch(texts)

            # Prepare data for database
            transcript_metadatas = []
            transcript_ids = []

            for idx, chunk in enumerate(chunks):
                metadata = {
                    "video_id": video_id,
                    "start_time": float(chunk["start_time"]),  # Convert numpy float64 to Python float
                    "end_time": float(chunk["end_time"]),      # Convert numpy float64 to Python float
                    "text": chunk["text"],
                    "video_filename": file.filename,
                }

                if group_id:
                    metadata["group_id"] = group_id

                transcript_metadatas.append(metadata)
                transcript_ids.append(f"{video_id}:transcript_{idx}")

            # Add to database
            transcript_db.add_transcripts(
                embeddings=transcript_embeddings.tolist(),
                metadatas=transcript_metadatas,
                ids=transcript_ids,
            )

            transcript_count = len(chunks)
            logger.info(f"Successfully indexed {transcript_count} transcript chunks")
        else:
            logger.warning("No transcript chunks generated")

        return VideoUploadResponse(
            video_id=video_id,
            frame_count=len(frames),
            transcript_chunks_count=transcript_count,
            message="Video processed successfully",
        )

    except Exception as e:
        logger.error(f"Error processing video: {e}", exc_info=True)

        # Cleanup: Delete all resources associated with the failed video
        try:
            logger.info(f"Cleaning up failed video upload for video_id={video_id}")

            # 1. Delete Pinecone vectors (frames)
            try:
                pc.delete_by_filter(
                    filter_dict={"video_id": {"$eq": video_id}},
                    modality="video_frame",
                    namespace=user_id,
                )
                logger.info(f"Deleted frame vectors from Pinecone for video_id={video_id}")
            except Exception as del_error:
                logger.error(f"Failed to delete frame vectors from Pinecone: {del_error}")

            # 2. Delete Pinecone vectors (transcripts)
            try:
                pc.delete_by_filter(
                    filter_dict={"video_id": {"$eq": video_id}},
                    modality="video_transcript",
                    namespace=user_id,
                )
                logger.info(f"Deleted transcript vectors from Pinecone for video_id={video_id}")
            except Exception as del_error:
                logger.error(f"Failed to delete transcript vectors from Pinecone: {del_error}")

            # 3. Delete frame images from storage
            try:
                sb.delete_frames_for_video(user_id, video_id)
                logger.info(f"Deleted frame images from storage for video_id={video_id}")
            except Exception as del_error:
                logger.error(f"Failed to delete frame images from storage: {del_error}")

            # 4. Delete video file from storage if it was uploaded
            if storage_path:
                try:
                    sb.delete_video_from_bucket(storage_path)
                    logger.info(f"Deleted video file from storage: {storage_path}")
                except Exception as del_error:
                    logger.error(f"Failed to delete video file from storage: {del_error}")

            # 5. Delete app_chunks records
            try:
                sb.supabase.table("app_chunks").delete().eq(
                    "doc_id", video_id
                ).eq("user_id", user_id).execute()
                logger.info(f"Deleted app_chunks records for video_id={video_id}")
            except Exception as del_error:
                logger.error(f"Failed to delete app_chunks records: {del_error}")

            # 6. Delete doc_meta record
            sb.supabase.table("app_doc_meta").delete().eq(
                "doc_id", video_id
            ).eq("user_id", user_id).execute()
            logger.info(f"Successfully deleted failed video record: video_id={video_id}")
        except Exception as cleanup_error:
            logger.error(f"Failed to cleanup after video processing failure: {cleanup_error}")

        raise HTTPException(500, detail=f"Video processing failed: {str(e)}")

    finally:
        # Clean up temporary file
        if temp_video_path and os.path.exists(temp_video_path):
            try:
                os.unlink(temp_video_path)
                logger.info(f"Cleaned up temporary file: {temp_video_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file: {e}")


@app.post("/api/v1/video/query", response_model=VideoQueryResponse)
async def query_video(request: VideoQueryRequest):
    """
    Query video content by text.

    Routes:
    - video_frames: Search video frames using CLIP embeddings
    - video_transcript: Search transcript chunks using text embeddings
    - video_combined: Search both frames and transcripts

    Args:
        request: Query request with user_id, query_text, route, top_k, and optional group_id

    Returns:
        VideoQueryResponse with matching results
    """
    logger.info(f"Received video query: user_id={request.user_id}, route={request.route}, query={request.query_text[:50]}...")

    if request.route not in ("video_frames", "video_transcript", "video_combined"):
        raise HTTPException(
            422,
            detail="route must be 'video_frames', 'video_transcript', or 'video_combined'"
        )

    try:
        # Initialize components
        clip_embedder = get_clip_embedder()
        transcript_embedder = get_transcript_embedder()

        # Initialize databases
        frame_db = VideoFrameDatabase(user_id=request.user_id)
        transcript_db = TranscriptDatabase(user_id=request.user_id)

        # Prepare filter
        where_filter = None
        if request.group_id:
            where_filter = {"group_id": {"$eq": request.group_id}}

        results = []

        if request.route == "video_frames":
            # Query frames
            query_embedding = clip_embedder.embed_text(request.query_text)
            results = frame_db.query(
                query_embedding=query_embedding.tolist(),
                n_results=request.top_k,
                where_filter=where_filter,
                diversify=True,
                diversity_weight=0.5,
            )

        elif request.route == "video_transcript":
            # Query transcripts
            query_embedding = transcript_embedder.embed_text(request.query_text)
            results = transcript_db.query(
                query_embedding=query_embedding.tolist(),
                n_results=request.top_k,
                where_filter=where_filter,
                diversify=True,
                diversity_weight=0.5,
            )

        elif request.route == "video_combined":
            # Query both frames and transcripts
            frame_embedding = clip_embedder.embed_text(request.query_text)
            transcript_embedding = transcript_embedder.embed_text(request.query_text)

            frame_results = frame_db.query(
                query_embedding=frame_embedding.tolist(),
                n_results=request.top_k,
                where_filter=where_filter,
                diversify=True,
                diversity_weight=0.5,
            )

            transcript_results = transcript_db.query(
                query_embedding=transcript_embedding.tolist(),
                n_results=request.top_k,
                where_filter=where_filter,
                diversify=True,
                diversity_weight=0.5,
            )

            results = {
                "frames": frame_results,
                "transcripts": transcript_results,
            }

        logger.info(f"Query completed successfully: {len(results) if isinstance(results, list) else 'combined'} results")

        return VideoQueryResponse(results=results)

    except Exception as e:
        logger.error(f"Error querying video: {e}", exc_info=True)
        raise HTTPException(500, detail=f"Video query failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8001"))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"Starting video query service on {host}:{port}")

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=os.getenv("RELOAD", "false").lower() == "true",
    )
