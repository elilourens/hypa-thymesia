"""
Supabase service for video storage and metadata management.
Follows the same structure as the main hypa-thymesia backend.
"""
import os
from typing import Optional, Dict, Any, List
from uuid import uuid4
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY environment variables.")

# Storage buckets
VIDEO_BUCKET = os.getenv("VIDEO_BUCKET", "videos")
VIDEO_FRAMES_BUCKET = os.getenv("VIDEO_FRAMES_BUCKET", "video-frames")

# Initialize Supabase client with persistent connection pool
_supabase_client: Optional[Client] = None


def get_supabase() -> Client:
    """Get or create Supabase client."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


# Expose supabase client for direct access
supabase = get_supabase()


# ============================================================================
# VIDEO UPLOAD
# ============================================================================


def upload_video_to_bucket(
    file_content: bytes,
    filename: str,
    user_id: str,
    bucket: str = VIDEO_BUCKET,
    mime_type: Optional[str] = None,
) -> Optional[str]:
    """
    Upload a video file to Supabase storage.

    Args:
        file_content: Video file bytes
        filename: Original filename
        user_id: User ID for path organization
        bucket: Storage bucket name
        mime_type: Optional MIME type (e.g., "video/mp4")

    Returns:
        Storage path if successful, None otherwise
    """
    supabase = get_supabase()

    # Validate video extension
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".mp4", ".avi", ".mov", ".mkv", ".webm"]:
        return None

    # Create unique path: user_id/uuid_filename
    file_path = f"{user_id}/{uuid4()}_{filename}"

    try:
        resp = supabase.storage.from_(bucket).upload(
            file_path,
            file_content,
            {"content-type": mime_type or "video/mp4"},
        )
        return file_path if resp else None
    except Exception as e:
        print(f"Error uploading video: {e}")
        return None


def delete_video_from_bucket(
    filepath: str,
    bucket: str = VIDEO_BUCKET
) -> bool:
    """
    Delete a video file from Supabase storage.

    Args:
        filepath: Storage path to delete
        bucket: Storage bucket name

    Returns:
        True if successful, False otherwise
    """
    supabase = get_supabase()
    try:
        res = supabase.storage.from_(bucket).remove([filepath])
        return any(obj.get("name") == filepath for obj in (res or []))
    except Exception as e:
        print(f"Error deleting video: {e}")
        return False


def get_video_public_url(
    filepath: str,
    bucket: str = VIDEO_BUCKET
) -> Optional[str]:
    """
    Get public URL for a video file.

    Args:
        filepath: Storage path
        bucket: Storage bucket name

    Returns:
        Public URL if successful, None otherwise
    """
    supabase = get_supabase()
    try:
        return supabase.storage.from_(bucket).get_public_url(filepath)
    except Exception as e:
        print(f"Error getting public URL: {e}")
        return None


# ============================================================================
# FRAME UPLOAD
# ============================================================================


def upload_frame_to_bucket(
    frame_bytes: bytes,
    user_id: str,
    video_id: str,
    frame_index: int,
    timestamp: float,
    bucket: str = VIDEO_FRAMES_BUCKET,
) -> Dict[str, str]:
    """
    Upload a video frame to Supabase storage.

    Args:
        frame_bytes: Frame image bytes (PNG/JPEG)
        user_id: User ID
        video_id: Video document ID
        frame_index: Frame number in video
        timestamp: Timestamp in seconds
        bucket: Storage bucket name

    Returns:
        Dictionary with bucket and storage_path
    """
    supabase = get_supabase()

    # Create path: user_id/video_id/frame_XXXXX.jpg
    filename = f"frame_{frame_index:06d}.jpg"
    storage_path = f"{user_id}/{video_id}/{filename}"

    try:
        supabase.storage.from_(bucket).upload(
            path=storage_path,
            file=frame_bytes,
            file_options={"content-type": "image/jpeg"}
        )
    except Exception:
        # Try update if upload fails (frame already exists)
        try:
            supabase.storage.from_(bucket).update(
                path=storage_path,
                file=frame_bytes,
                file_options={"content-type": "image/jpeg"}
            )
        except Exception as e:
            print(f"Error uploading frame: {e}")
            raise

    return {
        "bucket": bucket,
        "storage_path": storage_path,
    }


def upload_frame(
    frame,
    user_id: str,
    video_id: str,
    frame_filename: str,
    bucket: str = VIDEO_FRAMES_BUCKET,
) -> str:
    """
    Upload a video frame (numpy array or PIL Image) to Supabase storage.

    Args:
        frame: Frame as numpy array or PIL Image
        user_id: User ID
        video_id: Video document ID
        frame_filename: Filename to use (e.g., "video_id_frame_0.jpg")
        bucket: Storage bucket name

    Returns:
        Storage path
    """
    import cv2
    import numpy as np
    from io import BytesIO

    supabase = get_supabase()

    # Convert frame to JPEG bytes
    if isinstance(frame, np.ndarray):
        # Convert from OpenCV BGR to RGB if needed
        if len(frame.shape) == 3 and frame.shape[2] == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        # Encode as JPEG
        success, buffer = cv2.imencode('.jpg', frame)
        if not success:
            raise ValueError("Failed to encode frame as JPEG")
        frame_bytes = buffer.tobytes()
    else:
        # Assume PIL Image
        buffer = BytesIO()
        frame.save(buffer, format='JPEG')
        frame_bytes = buffer.getvalue()

    # Create path: user_id/video_id/filename
    storage_path = f"{user_id}/{video_id}/{frame_filename}"

    try:
        supabase.storage.from_(bucket).upload(
            path=storage_path,
            file=frame_bytes,
            file_options={"content-type": "image/jpeg"}
        )
    except Exception:
        # Try update if upload fails (frame already exists)
        try:
            supabase.storage.from_(bucket).update(
                path=storage_path,
                file=frame_bytes,
                file_options={"content-type": "image/jpeg"}
            )
        except Exception as e:
            print(f"Error uploading frame: {e}")
            raise

    return storage_path


def delete_frames_for_video(
    user_id: str,
    video_id: str,
    bucket: str = VIDEO_FRAMES_BUCKET
) -> bool:
    """
    Delete all frames for a video.

    Args:
        user_id: User ID
        video_id: Video document ID
        bucket: Storage bucket name

    Returns:
        True if successful, False otherwise
    """
    supabase = get_supabase()
    try:
        # List all files in the video's folder
        prefix = f"{user_id}/{video_id}/"
        files = supabase.storage.from_(bucket).list(prefix)

        if files:
            file_paths = [f"{prefix}{file['name']}" for file in files]
            supabase.storage.from_(bucket).remove(file_paths)

        return True
    except Exception as e:
        print(f"Error deleting frames: {e}")
        return False


# ============================================================================
# DATABASE OPERATIONS (DEPRECATED - Video data now stored in unified schema)
# ============================================================================
# Videos are stored in app_doc_meta with modality='video'
# Video frames and transcripts are stored in app_chunks with modality='video_frame'/'video_transcript'
# All database operations are handled by the main backend service
