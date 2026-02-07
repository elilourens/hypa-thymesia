"""Image thumbnail generation service for Supabase storage."""

import logging
import cv2
import numpy as np
import httpx
from typing import Optional
from supabase import Client, create_client
from core.config import settings

logger = logging.getLogger(__name__)


class ThumbnailService:
    """Handles image thumbnail generation and storage in Supabase."""

    def __init__(self, supabase: Client):
        self.supabase = supabase
        self.bucket = "videos"  # Reuse existing bucket
        self.thumbnail_width = 300  # Smaller than video thumbnails (640px)
        self.jpeg_quality = 85  # Good balance between quality and size
        # Create a separate storage client with explicit service_role credentials
        self.storage_client = create_client(settings.supabase_url, settings.supabase_key)

    def _generate_thumbnail(self, image_bytes: bytes) -> Optional[bytes]:
        """
        Generate thumbnail from image bytes using OpenCV.

        Args:
            image_bytes: Raw image file bytes

        Returns:
            JPEG-encoded thumbnail bytes or None if generation fails
        """
        try:
            # Decode image from bytes
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                logger.warning("Failed to decode image with OpenCV")
                return None

            # Resize to thumbnail dimensions (maintain aspect ratio)
            height, width = img.shape[:2]
            aspect_ratio = width / height
            thumb_width = self.thumbnail_width
            thumb_height = int(thumb_width / aspect_ratio)
            resized = cv2.resize(img, (thumb_width, thumb_height))

            # Encode as JPEG
            success, jpeg_bytes = cv2.imencode(
                '.jpg',
                resized,
                [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
            )

            if not success:
                logger.warning("Failed to encode thumbnail as JPEG")
                return None

            return jpeg_bytes.tobytes()

        except Exception as e:
            logger.error(f"Error generating thumbnail: {e}")
            return None

    def upload_thumbnail(
        self,
        doc_id: str,
        thumbnail_bytes: bytes
    ) -> Optional[str]:
        """
        Upload thumbnail to Supabase Storage.

        Args:
            doc_id: Document ID (used as filename)
            thumbnail_bytes: JPEG thumbnail bytes

        Returns:
            Storage path (e.g., 'thumbnails/{doc_id}.jpg') or None on failure
        """
        try:
            thumbnail_path = f"thumbnails/{doc_id}.jpg"

            # Use storage_client with explicit service_role credentials
            self.storage_client.storage.from_(self.bucket).upload(
                thumbnail_path,
                thumbnail_bytes,
                file_options={"content-type": "image/jpeg", "upsert": "true"}
            )

            logger.info(f"Thumbnail uploaded: {thumbnail_path}")
            return thumbnail_path

        except Exception as e:
            logger.error(f"Error uploading thumbnail: {e}")
            return None

    def get_signed_url(
        self,
        thumbnail_path: str,
        expires_in: int = 3600
    ) -> Optional[str]:
        """
        Generate signed URL for thumbnail access.

        Args:
            thumbnail_path: Storage path (e.g., 'thumbnails/{doc_id}.jpg')
            expires_in: URL expiration in seconds (default 1 hour)

        Returns:
            Signed URL string or None on failure
        """
        try:
            signed_url = self.supabase.storage.from_(self.bucket).create_signed_url(
                path=thumbnail_path,
                expires_in=expires_in
            )

            if not signed_url:
                return None

            return signed_url["signedURL"]

        except Exception as e:
            logger.error(f"Error getting signed thumbnail URL: {e}")
            return None
