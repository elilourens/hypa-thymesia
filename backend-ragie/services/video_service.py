"""Video handling service for Supabase storage and Ragie processing."""

import logging
import tempfile
import os
import asyncio
from typing import Optional
from fastapi import UploadFile
from supabase import Client
from .ragie_service import RagieService
from core.config import settings
import cv2
import numpy as np
from io import BytesIO
import uuid

logger = logging.getLogger(__name__)


class VideoService:
    """Handles video uploads to Supabase and Ragie processing."""

    def __init__(self, supabase: Client, ragie_service: RagieService):
        self.supabase = supabase
        self.ragie_service = ragie_service

    def _extract_first_frame(self, video_bytes: bytes) -> Optional[bytes]:
        """
        Extract the first frame from video bytes.

        Args:
            video_bytes: Raw video file bytes

        Returns:
            JPEG-encoded image bytes or None if extraction fails
        """
        try:
            # Write bytes to temporary file for OpenCV
            temp_video = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            temp_video.write(video_bytes)
            temp_video.close()

            # Open video with OpenCV
            cap = cv2.VideoCapture(temp_video.name)
            if not cap.isOpened():
                logger.warning("Failed to open video with OpenCV")
                return None

            # Read first frame
            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                logger.warning("Failed to read first frame from video")
                return None

            # Resize frame to reasonable thumbnail size (e.g., 640x360)
            height, width = frame.shape[:2]
            aspect_ratio = width / height
            thumb_width = 640
            thumb_height = int(thumb_width / aspect_ratio)
            frame = cv2.resize(frame, (thumb_width, thumb_height))

            # Encode frame as JPEG
            success, jpeg_bytes = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 95])

            # Clean up temp file
            try:
                os.unlink(temp_video.name)
            except Exception as e:
                logger.warning(f"Failed to clean up temp video file: {e}")

            if not success:
                logger.warning("Failed to encode frame as JPEG")
                return None

            return jpeg_bytes.tobytes()

        except Exception as e:
            logger.error(f"Error extracting first frame: {e}")
            return None

    async def upload_video(
        self,
        file: UploadFile,
        user_id: str,
        group_id: Optional[str] = None,
    ) -> dict:
        """
        Upload video to Supabase Storage and create ragie_documents record.

        Args:
            file: Video file to upload
            user_id: User ID uploading the video
            group_id: Optional group ID to organize video

        Returns:
            Dictionary with video metadata
        """
        try:
            # Get file content
            file_content = await file.read()
            file_size = len(file_content)

            # Validate file is MP4
            if file.content_type not in ["video/mp4", "application/octet-stream"]:
                if not file.filename.endswith(".mp4"):
                    raise ValueError("Only MP4 videos are supported")

            # Upload to Supabase Storage (pass raw bytes directly, like documents work)
            storage_path = f"{user_id}/{file.filename}"
            try:
                response = self.supabase.storage.from_("videos").upload(
                    storage_path,
                    file_content,
                    file_options={"content-type": "video/mp4", "upsert": "true"}
                )
                if not response:
                    raise Exception("Storage upload returned empty response")
            except Exception as e:
                logger.error(f"Storage upload failed: {e}")
                raise Exception(f"Failed to upload video to storage: {str(e)}")

            # Save bytes to temp file (to avoid re-downloading for Ragie processing)
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            temp_file.write(file_content)
            temp_file.close()
            temp_file_path = temp_file.name
            logger.info(f"Saved video to temp file: {temp_file_path}")

            # Create database record in ragie_documents
            # Note: ragie_document_id will be updated after Ragie upload completes
            doc_record = self.supabase.table("ragie_documents").insert({
                "user_id": user_id,
                "group_id": group_id,
                "filename": file.filename,
                "mime_type": file.content_type or "video/mp4",
                "file_size_bytes": file_size,
                "status": "pending",
                "source": "upload",
                "storage_bucket": "videos",
                "storage_path": storage_path
            }).execute()

            if not doc_record.data:
                raise Exception("Failed to create document record in database")

            doc = doc_record.data[0]

            # Extract and upload first frame as thumbnail (now we have the document ID)
            thumbnail_path = None
            frame_bytes = self._extract_first_frame(file_content)
            if frame_bytes:
                try:
                    # Use ragie_documents.id as thumbnail name for easy lookup during search
                    thumbnail_path = f"thumbnails/{doc['id']}.jpg"
                    self.supabase.storage.from_("videos").upload(
                        thumbnail_path,
                        frame_bytes,
                        file_options={"content-type": "image/jpeg", "upsert": "true"}
                    )
                    logger.info(f"Thumbnail uploaded to: {thumbnail_path}")
                except Exception as e:
                    logger.warning(f"Failed to upload thumbnail: {e}")
                    # Continue without thumbnail, don't fail the upload

            logger.info(f"Video uploaded: {file.filename} for user {user_id}")

            return {
                "id": doc["id"],
                "filename": doc["filename"],
                "storage_path": doc["storage_path"],
                "file_size_bytes": doc["file_size_bytes"],
                "processing_status": doc["status"],
                "created_at": doc["created_at"],
                "_temp_file_path": temp_file_path,  # Internal use only
                "_thumbnail_path": thumbnail_path  # Internal use only
            }

        except Exception as e:
            logger.error(f"Error uploading video: {e}")
            raise

    async def process_video_with_ragie(
        self,
        video_id: str,
        user_id: str,
        temp_file_path: Optional[str] = None,
        thumbnail_path: Optional[str] = None,
    ) -> dict:
        """
        Process video with Ragie.ai.

        If RAGIE_WEBHOOK_SECRET is configured (production):
        - Submits video to Ragie and returns immediately with status "partitioning"
        - Ragie calls webhook endpoint when processing completes
        - Webhook updates status to "ready" and stores chunks

        If RAGIE_WEBHOOK_SECRET is not configured (local development):
        - Submits video to Ragie and polls for completion
        - Returns when status becomes "ready" (max 60 attempts, 30 min timeout)

        Args:
            video_id: Document ID (from ragie_documents) to process
            user_id: User ID (for RLS)
            temp_file_path: Path to temporary video file (to avoid re-downloading)
            thumbnail_path: Storage path of extracted first frame thumbnail

        Returns:
            Processing result dict with status and ragie_document_id
        """
        try:
            # Get ragie_documents record
            doc_response = self.supabase.table("ragie_documents").select(
                "*"
            ).eq("id", video_id).eq("user_id", user_id).single().execute()

            if not doc_response.data:
                raise Exception(f"Document {video_id} not found")

            doc = doc_response.data

            # Update status to processing
            self.supabase.table("ragie_documents").update({
                "status": "partitioning"
            }).eq("id", video_id).execute()

            # Read video from temp file or download from storage
            from io import BytesIO
            from fastapi import UploadFile

            if temp_file_path and os.path.exists(temp_file_path):
                # Use cached temp file (avoid re-downloading)
                logger.info(f"Reading video from temp file: {temp_file_path}")
                with open(temp_file_path, "rb") as f:
                    video_bytes = f.read()
            else:
                # Fallback: download from Supabase Storage
                logger.info(f"Downloading video from storage: {doc['storage_path']}")
                signed_url = self.supabase.storage.from_("videos").create_signed_url(
                    path=doc["storage_path"],
                    expires_in=3600
                )
                if not signed_url:
                    raise Exception("Failed to create signed URL")

                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.get(signed_url["signedURL"])
                    response.raise_for_status()
                    video_bytes = response.content

            # Create an UploadFile object for Ragie
            video_file = UploadFile(
                file=BytesIO(video_bytes),
                size=len(video_bytes),
                filename=doc["filename"],
                headers={"content-type": "video/mp4"}
            )

            # Send to Ragie for processing
            ragie_doc = await self.ragie_service.upload_document(
                file=video_file,
                user_id=user_id,
                metadata={"original_storage_path": doc["storage_path"]}
            )

            # Store Ragie document ID in database
            # Status is already "partitioning" from earlier update
            self.supabase.table("ragie_documents").update({
                "ragie_document_id": str(ragie_doc.id)
            }).eq("id", video_id).execute()

            # Calculate page_count from file size (100MB = 5 pages)
            file_size_mb = doc["file_size_bytes"] / (1024 * 1024)
            page_count = max(1, round(file_size_mb / 20 * 5))
            self.supabase.table("ragie_documents").update({
                "page_count": page_count
            }).eq("id", video_id).execute()

            # Check if webhook is configured
            if settings.ragie_webhook_secret:
                # Production: Webhook will handle processing updates
                logger.info(f"Video {video_id} submitted to Ragie (doc_id: {ragie_doc.id}). Webhook will handle processing updates.")
                return {
                    "document_id": video_id,
                    "ragie_document_id": str(ragie_doc.id),
                    "status": "partitioning"
                }
            else:
                # Local development: Poll for completion
                logger.info(f"Video {video_id} submitted to Ragie. Polling for completion (no webhook configured)...")
                return await self._poll_document_status(video_id, user_id, str(ragie_doc.id))

        except Exception as e:
            logger.error(f"Error processing video with Ragie: {e}")

            # Update status to failed
            self.supabase.table("ragie_documents").update({
                "status": "failed",
                "processing_error": str(e)
            }).eq("id", video_id).execute()

            raise

        finally:
            # Clean up temp file if it exists
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                    logger.info(f"Cleaned up temp file: {temp_file_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temp file {temp_file_path}: {e}")

    async def _poll_document_status(
        self,
        video_id: str,
        user_id: str,
        ragie_document_id: str,
        max_attempts: int = 60,
        poll_interval: int = 30
    ) -> dict:
        """
        Poll Ragie for document processing completion (local development fallback).

        Args:
            video_id: Local document ID
            user_id: User ID (for RLS)
            ragie_document_id: Ragie document ID
            max_attempts: Maximum polling attempts (60 * 30s = 30 minutes max)
            poll_interval: Seconds between polls

        Returns:
            Processing result dict with status and document info
        """
        attempt = 0
        while attempt < max_attempts:
            attempt += 1
            try:
                # Poll Ragie for status
                ragie_doc = await self.ragie_service.get_document_status(ragie_document_id)

                if ragie_doc.status in ("ready", "indexed", "keyword_indexed"):
                    logger.info(f"Video {video_id} processing completed with status: {ragie_doc.status}")

                    # Update document in database
                    update_data = {"status": ragie_doc.status}
                    if hasattr(ragie_doc, "chunk_count") and ragie_doc.chunk_count:
                        update_data["chunk_count"] = int(ragie_doc.chunk_count)
                    if hasattr(ragie_doc, "page_count") and ragie_doc.page_count:
                        update_data["page_count"] = int(ragie_doc.page_count)

                    self.supabase.table("ragie_documents").update(update_data).eq(
                        "id", video_id
                    ).execute()

                    return {
                        "document_id": video_id,
                        "ragie_document_id": ragie_document_id,
                        "status": ragie_doc.status
                    }

                elif ragie_doc.status == "failed":
                    error_msg = getattr(ragie_doc, "error", "Processing failed")
                    logger.error(f"Video {video_id} processing failed: {error_msg}")

                    self.supabase.table("ragie_documents").update({
                        "status": "failed",
                        "processing_error": error_msg
                    }).eq("id", video_id).execute()

                    raise Exception(f"Ragie processing failed: {error_msg}")

                else:
                    # Still processing
                    logger.info(f"Video {video_id} still processing (attempt {attempt}/{max_attempts}): {ragie_doc.status}")

            except Exception as e:
                if "failed" in str(e).lower():
                    raise
                logger.warning(f"Poll attempt {attempt} failed: {e}")

            # Wait before next poll (except on last attempt)
            if attempt < max_attempts:
                await asyncio.sleep(poll_interval)

        # Timeout reached
        logger.error(f"Video {video_id} polling timeout after {max_attempts} attempts ({max_attempts * poll_interval}s)")
        self.supabase.table("ragie_documents").update({
            "status": "failed",
            "processing_error": f"Processing timeout after {max_attempts * poll_interval} seconds"
        }).eq("id", video_id).execute()

        raise Exception(f"Document processing timeout (max {max_attempts * poll_interval} seconds)")

    def get_signed_thumbnail_url(
        self,
        thumbnail_path: Optional[str],
        expires_in: int = 3600
    ) -> Optional[str]:
        """
        Get signed URL for thumbnail (requires auth).

        Args:
            thumbnail_path: Storage path of thumbnail (e.g., 'thumbnails/uuid.jpg')
            expires_in: URL expiration time in seconds (default 1 hour)

        Returns:
            Signed URL string or None if path is invalid
        """
        try:
            if not thumbnail_path:
                return None

            signed_url = self.supabase.storage.from_("videos").create_signed_url(
                path=thumbnail_path,
                expires_in=expires_in
            )

            if not signed_url:
                return None

            return signed_url["signedURL"]

        except Exception as e:
            logger.error(f"Error getting signed thumbnail URL: {e}")
            return None

    async def get_signed_video_url(
        self,
        video_id: str,
        user_id: str,
        expires_in: int = 3600
    ) -> str:
        """
        Get signed URL for video streaming.

        Args:
            video_id: Document ID (from ragie_documents)
            user_id: User ID (for RLS verification)
            expires_in: URL expiration time in seconds (default 1 hour)

        Returns:
            Signed URL string
        """
        try:
            # Verify user owns the document
            doc_response = self.supabase.table("ragie_documents").select(
                "storage_path"
            ).eq("id", video_id).eq("user_id", user_id).single().execute()

            if not doc_response.data:
                raise Exception("Document not found or access denied")

            doc = doc_response.data
            storage_path = doc["storage_path"]

            # Get signed URL
            signed_url = self.supabase.storage.from_("videos").create_signed_url(
                path=storage_path,
                expires_in=expires_in
            )

            if not signed_url:
                raise Exception("Failed to create signed URL")

            return signed_url["signedURL"]

        except Exception as e:
            logger.error(f"Error getting signed URL: {e}")
            raise

    async def delete_document(self, document_id: str, user_id: str) -> None:
        """
        Delete a ragie_documents record and clean up associated files.
        Cascade delete handles video_chunks automatically.

        Args:
            document_id: Document ID (from ragie_documents)
            user_id: User ID (for RLS verification)
        """
        try:
            # Get document to find storage paths and ragie_document_id
            doc_response = self.supabase.table("ragie_documents").select(
                "storage_path, ragie_metadata, ragie_document_id"
            ).eq("id", document_id).eq("user_id", user_id).single().execute()

            if not doc_response.data:
                raise Exception("Document not found or access denied")

            doc = doc_response.data

            # Delete from Ragie if this document was processed with Ragie
            if doc.get("ragie_document_id"):
                try:
                    await self.ragie_service.delete_document(doc["ragie_document_id"])
                    logger.info(f"Deleted document {document_id} from Ragie")
                except Exception as e:
                    logger.warning(f"Failed to delete document {document_id} from Ragie: {e}")
                    # Continue with storage and database deletion anyway

            # Get all chunks to find thumbnail paths
            chunks_response = self.supabase.table("video_chunks").select(
                "thumbnail_url"
            ).eq("ragie_document_id", document_id).execute()

            chunks = chunks_response.data or []

            # Collect all storage paths to delete
            paths_to_delete = []
            if doc.get("storage_path"):
                paths_to_delete.append(doc["storage_path"])

            # Add unique thumbnail paths from chunks
            thumbnails = set()
            for chunk in chunks:
                if chunk.get("thumbnail_url"):
                    thumbnails.add(chunk["thumbnail_url"])

            paths_to_delete.extend(thumbnails)

            # Also add the expected thumbnail path (in case video_chunks is empty or incomplete)
            # Thumbnails are always stored as thumbnails/{document_id}.jpg
            expected_thumbnail_path = f"thumbnails/{document_id}.jpg"
            if expected_thumbnail_path not in paths_to_delete:
                paths_to_delete.append(expected_thumbnail_path)

            # Delete files from storage
            if paths_to_delete:
                try:
                    self.supabase.storage.from_("videos").remove(paths_to_delete)
                    logger.info(f"Deleted {len(paths_to_delete)} files from storage for document {document_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete some files from storage: {e}")
                    # Continue with database deletion anyway

            # Delete document (cascade delete will handle video_chunks)
            self.supabase.table("ragie_documents").delete().eq("id", document_id).execute()

            logger.info(f"Deleted document {document_id} and all associated data")

        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            raise
