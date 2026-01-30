"""Video handling service for Supabase storage and Ragie processing."""

import logging
import tempfile
import os
from typing import Optional
from fastapi import UploadFile
from supabase import Client
from .ragie_service import RagieService

logger = logging.getLogger(__name__)


class VideoService:
    """Handles video uploads to Supabase and Ragie processing."""

    def __init__(self, supabase: Client, ragie_service: RagieService):
        self.supabase = supabase
        self.ragie_service = ragie_service

    async def upload_video(
        self,
        file: UploadFile,
        user_id: str,
        group_id: Optional[str] = None,
    ) -> dict:
        """
        Upload video to Supabase Storage and create database record.

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

            # Create database record
            video_record = self.supabase.table("videos").insert({
                "user_id": user_id,
                "group_id": group_id,
                "filename": file.filename,
                "storage_bucket": "videos",
                "storage_path": storage_path,
                "mime_type": file.content_type or "video/mp4",
                "file_size_bytes": file_size,
                "processing_status": "queued"
            }).execute()

            if not video_record.data:
                raise Exception("Failed to create video record in database")

            video = video_record.data[0]

            logger.info(f"Video uploaded: {file.filename} for user {user_id}")

            return {
                "id": video["id"],
                "filename": video["filename"],
                "storage_path": video["storage_path"],
                "file_size_bytes": video["file_size_bytes"],
                "processing_status": video["processing_status"],
                "created_at": video["created_at"],
                "_temp_file_path": temp_file_path  # Internal use only
            }

        except Exception as e:
            logger.error(f"Error uploading video: {e}")
            raise

    async def process_video_with_ragie(
        self,
        video_id: str,
        user_id: str,
        temp_file_path: Optional[str] = None,
    ) -> dict:
        """
        Process video with Ragie.ai.

        1. Read video from temp file (or download from Supabase if not cached)
        2. Send to Ragie for processing
        3. Wait for Ragie to complete
        4. Retrieve chunks from Ragie
        5. Store chunks in video_chunks table
        6. Update video processing_status

        Args:
            video_id: Video ID to process
            user_id: User ID (for RLS)
            temp_file_path: Path to temporary video file (to avoid re-downloading)

        Returns:
            Processing result
        """
        try:
            # Get video record
            video_response = self.supabase.table("videos").select(
                "*"
            ).eq("id", video_id).eq("user_id", user_id).single().execute()

            if not video_response.data:
                raise Exception(f"Video {video_id} not found")

            video = video_response.data

            # Update status to processing
            self.supabase.table("videos").update({
                "processing_status": "processing"
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
                logger.info(f"Downloading video from storage: {video['storage_path']}")
                signed_url = self.supabase.storage.from_("videos").create_signed_url(
                    path=video["storage_path"],
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
                filename=video["filename"],
                headers={"content-type": "video/mp4"}
            )

            # Send to Ragie for processing
            ragie_doc = await self.ragie_service.upload_document(
                file=video_file,
                user_id=user_id,
                metadata={"original_storage_path": video["storage_path"]}
            )

            # Wait for Ragie processing (polling)
            import asyncio
            max_attempts = 60  # 60 attempts × 30 seconds = 30 minutes total timeout
            attempt = 0
            while attempt < max_attempts:
                status_response = await self.ragie_service.get_document_status(
                    ragie_doc.id
                )

                if status_response.status == "completed":
                    break

                if status_response.status == "failed":
                    raise Exception(f"Ragie processing failed: {status_response}")

                await asyncio.sleep(30)  # Poll every 30 seconds (2 requests per minute)
                attempt += 1

            if attempt >= max_attempts:
                raise Exception("Ragie processing timeout")

            # Get chunks from Ragie
            chunks_response = await self.ragie_service.retrieve(
                query="",  # Get all chunks
                user_id=user_id,
                top_k=1000,  # Get all chunks
                rerank=False
            )

            # Filter chunks for this document
            video_chunks = [
                chunk for chunk in chunks_response.scored_chunks
                if chunk.document_id == ragie_doc.id
            ]

            # Store chunks in database
            chunk_records = []
            for i, chunk in enumerate(video_chunks):
                # Extract timing info from chunk metadata
                start_time = chunk.metadata.get("start_time", 0) if hasattr(chunk, "metadata") else 0
                end_time = chunk.metadata.get("end_time", 0) if hasattr(chunk, "metadata") else 0

                chunk_record = {
                    "video_id": video_id,
                    "user_id": user_id,
                    "ragie_chunk_id": chunk.chunk_id,
                    "ragie_document_id": str(ragie_doc.id),
                    "chunk_index": i,
                    "start_time": start_time,
                    "end_time": end_time,
                    "audio_transcript": chunk.text if hasattr(chunk, "text") else "",
                    "video_description": chunk.metadata.get("video_description", "") if hasattr(chunk, "metadata") else ""
                }
                chunk_records.append(chunk_record)

            if chunk_records:
                self.supabase.table("video_chunks").insert(chunk_records).execute()

            # Calculate page_count from file size (100MB = 5 pages)
            # Formula: pages = (file_size_bytes / 100MB) * 5 = file_size_bytes / 20MB
            file_size_mb = video["file_size_bytes"] / (1024 * 1024)
            page_count = max(1, round(file_size_mb / 20 * 5, 1))  # Minimum 1 page, round to 1 decimal

            # Update video record
            self.supabase.table("videos").update({
                "processing_status": "completed",
                "ragie_document_id": str(ragie_doc.id),
                "chunk_count": len(chunk_records),
                "page_count": page_count
            }).eq("id", video_id).execute()

            logger.info(f"Video {video_id} processed successfully with {len(chunk_records)} chunks")

            return {
                "video_id": video_id,
                "ragie_document_id": str(ragie_doc.id),
                "chunk_count": len(chunk_records),
                "status": "completed"
            }

        except Exception as e:
            logger.error(f"Error processing video with Ragie: {e}")

            # Update status to failed
            self.supabase.table("videos").update({
                "processing_status": "failed",
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

    async def get_signed_video_url(
        self,
        video_id: str,
        user_id: str,
        expires_in: int = 3600
    ) -> str:
        """
        Get signed URL for video streaming.

        Args:
            video_id: Video ID
            user_id: User ID (for RLS verification)
            expires_in: URL expiration time in seconds (default 1 hour)

        Returns:
            Signed URL string
        """
        try:
            # Verify user owns the video
            video_response = self.supabase.table("videos").select(
                "storage_path"
            ).eq("id", video_id).eq("user_id", user_id).single().execute()

            if not video_response.data:
                raise Exception("Video not found or access denied")

            video = video_response.data
            storage_path = video["storage_path"]

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
