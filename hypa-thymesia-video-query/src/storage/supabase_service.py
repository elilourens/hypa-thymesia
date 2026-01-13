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
# DATABASE OPERATIONS
# ============================================================================


def insert_video_metadata(
    user_id: str,
    video_id: str,
    filename: str,
    storage_path: str,
    bucket: str,
    mime_type: str,
    duration_seconds: float,
    fps: float,
    width: int,
    height: int,
    size_bytes: int,
    group_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Insert video metadata into app_video_docs table.

    Args:
        user_id: User ID
        video_id: Unique video document ID
        filename: Original filename
        storage_path: Path in storage bucket
        bucket: Storage bucket name
        mime_type: Video MIME type
        duration_seconds: Video duration in seconds
        fps: Frames per second
        width: Video width in pixels
        height: Video height in pixels
        size_bytes: File size in bytes
        group_id: Optional group ID for organization

    Returns:
        Inserted row data
    """
    supabase = get_supabase()

    row = {
        "video_id": video_id,
        "user_id": user_id,
        "filename": filename,
        "storage_path": storage_path,
        "bucket": bucket,
        "mime_type": mime_type,
        "duration_seconds": duration_seconds,
        "fps": fps,
        "width": width,
        "height": height,
        "size_bytes": size_bytes,
        "group_id": group_id,
        "created_at": datetime.utcnow().isoformat(),
    }

    data = supabase.table("app_video_docs").insert(row).execute()
    return data.data[0] if data.data else {}


def insert_frame_chunks(
    user_id: str,
    video_id: str,
    frames: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Insert frame chunks into app_video_frame_chunks table.

    Args:
        user_id: User ID
        video_id: Video document ID
        frames: List of frame dictionaries with keys:
            - frame_index: int
            - timestamp: float
            - storage_path: str
            - bucket: str
            - scene_id: Optional[int]

    Returns:
        Inserted rows
    """
    supabase = get_supabase()

    rows = []
    for frame in frames:
        rows.append({
            "chunk_id": str(uuid4()),
            "video_id": video_id,
            "user_id": user_id,
            "frame_index": frame["frame_index"],
            "timestamp": frame["timestamp"],
            "storage_path": frame["storage_path"],
            "bucket": frame["bucket"],
            "scene_id": frame.get("scene_id"),
            "modality": "video_frame",
        })

    data = supabase.table("app_video_frame_chunks").insert(rows).execute()
    return data.data or []


def insert_transcript_chunks(
    user_id: str,
    video_id: str,
    transcripts: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Insert transcript chunks into app_video_transcript_chunks table.

    Args:
        user_id: User ID
        video_id: Video document ID
        transcripts: List of transcript dictionaries with keys:
            - start_time: float
            - end_time: float
            - text: str

    Returns:
        Inserted rows
    """
    supabase = get_supabase()

    rows = []
    for idx, transcript in enumerate(transcripts):
        rows.append({
            "chunk_id": str(uuid4()),
            "video_id": video_id,
            "user_id": user_id,
            "chunk_index": idx,
            "start_time": transcript["start_time"],
            "end_time": transcript["end_time"],
            "text": transcript["text"],
            "modality": "video_transcript",
        })

    data = supabase.table("app_video_transcript_chunks").insert(rows).execute()
    return data.data or []


def register_vectors(
    rows: List[Dict[str, Any]]
) -> None:
    """
    Register vectors in app_video_vector_registry table.

    Args:
        rows: List of dictionaries with keys:
            - vector_id: str (format: "chunk_id:embedding_version")
            - chunk_id: str
            - embedding_model: str
            - embedding_version: int
            - modality: str ("video_frame" or "video_transcript")
    """
    supabase = get_supabase()
    if rows:
        supabase.table("app_video_vector_registry").upsert(rows).execute()


def get_video_metadata(
    user_id: str,
    video_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Get video metadata by ID.

    Args:
        user_id: User ID
        video_id: Video document ID

    Returns:
        Video metadata dictionary or None
    """
    supabase = get_supabase()

    data = (
        supabase.table("app_video_docs")
        .select("*")
        .eq("video_id", video_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )

    return data.data[0] if data.data else None


def delete_video_document(
    user_id: str,
    video_id: str,
) -> bool:
    """
    Delete video document and all associated data (cascades to chunks and vectors).

    Args:
        user_id: User ID
        video_id: Video document ID

    Returns:
        True if successful, False otherwise
    """
    supabase = get_supabase()

    try:
        # Delete from app_video_docs (should cascade to chunks and vectors)
        supabase.table("app_video_docs").delete().eq(
            "video_id", video_id
        ).eq("user_id", user_id).execute()

        return True
    except Exception as e:
        print(f"Error deleting video document: {e}")
        return False


def list_user_videos(
    user_id: str,
    group_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    List all videos for a user, optionally filtered by group.

    Args:
        user_id: User ID
        group_id: Optional group ID filter

    Returns:
        List of video metadata dictionaries
    """
    supabase = get_supabase()

    query = supabase.table("app_video_docs").select("*").eq("user_id", user_id)

    if group_id:
        query = query.eq("group_id", group_id)

    data = query.execute()
    return data.data or []
