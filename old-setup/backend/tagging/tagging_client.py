"""
HTTP client for the Tagging Microservice.
Replaces direct CLIP/OWL-ViT/Ollama calls with HTTP calls to the microservice.
"""

import asyncio
import base64
import logging
import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class DocumentTag:
    """Represents a document tag from the microservice."""
    tag_name: str
    category: str
    confidence: float
    reasoning: Optional[str] = None


@dataclass
class ImageTag:
    """Represents an image tag from the microservice."""
    label: str
    confidence: float
    bbox: Optional[Dict[str, int]] = None
    verified: bool = False


class TaggingServiceClient:
    """HTTP client for communicating with the tagging microservice."""

    def __init__(
        self,
        base_url: str = None,
        timeout: int = 120
    ):
        """
        Initialize the tagging service client.

        Args:
            base_url: Base URL of the formatting/tagging microservice
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or os.getenv(
            "FORMATTING_SERVICE_URL",
            "http://localhost:8002"
        )
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

        logger.info(f"Initialized TaggingServiceClient with base_url={self.base_url}")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ========================================================================
    # Document Tagging
    # ========================================================================

    async def tag_document(
        self,
        text_content: str,
        filename: str = "",
        min_confidence: float = 0.5
    ) -> Dict[str, Any]:
        """
        Tag a document via the microservice.

        Args:
            text_content: Full text content of the document
            filename: Original filename for context
            min_confidence: Minimum confidence threshold

        Returns:
            Dict with 'tags', 'processing_time_ms', 'success', etc.
        """
        if not text_content or not text_content.strip():
            logger.warning("Empty text provided for document tagging")
            return {"tags": [], "success": False, "error": "Empty text"}

        try:
            client = await self._get_client()

            response = await client.post(
                "/api/v1/tagging/tag-document",
                json={
                    "text_content": text_content,
                    "filename": filename,
                    "min_confidence": min_confidence
                }
            )
            response.raise_for_status()

            result = response.json()

            if result.get("success"):
                # Convert to DocumentTag objects
                tags = [
                    DocumentTag(
                        tag_name=t["tag_name"],
                        category=t["category"],
                        confidence=t["confidence"],
                        reasoning=t.get("reasoning")
                    )
                    for t in result.get("tags", [])
                ]
                return {
                    "tags": tags,
                    "processing_time_ms": result.get("processing_time_ms", 0),
                    "preview_chars": result.get("preview_chars", 0),
                    "total_chars": result.get("total_chars", 0),
                    "success": True
                }
            else:
                logger.warning(f"Document tagging failed: {result.get('error')}")
                return {
                    "tags": [],
                    "success": False,
                    "error": result.get("error", "Unknown error")
                }

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error tagging document: {e.response.status_code}")
            return {"tags": [], "success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Failed to tag document via microservice: {e}", exc_info=True)
            return {"tags": [], "success": False, "error": str(e)}

    async def batch_tag_documents(
        self,
        documents: List[Dict[str, str]],
        min_confidence: float = 0.5,
        max_concurrent: int = 6
    ) -> Dict[str, Any]:
        """
        Tag multiple documents via the microservice.

        Args:
            documents: List of dicts with 'doc_id', 'text_content', and optional 'filename'
            min_confidence: Minimum confidence threshold
            max_concurrent: Maximum concurrent requests

        Returns:
            Dict with 'results' list and summary stats
        """
        if not documents:
            return {"results": [], "successful": 0, "failed": 0}

        try:
            client = await self._get_client()

            response = await client.post(
                "/api/v1/tagging/batch-tag-documents",
                json={
                    "documents": documents,
                    "min_confidence": min_confidence,
                    "max_concurrent": max_concurrent
                },
                timeout=max(self.timeout, len(documents) * 10)
            )
            response.raise_for_status()

            result = response.json()

            # Process results
            processed_results = []
            for doc_result in result.get("results", []):
                tags = [
                    DocumentTag(
                        tag_name=t["tag_name"],
                        category=t["category"],
                        confidence=t["confidence"],
                        reasoning=t.get("reasoning")
                    )
                    for t in doc_result.get("tags", [])
                ]
                processed_results.append({
                    "doc_id": doc_result["doc_id"],
                    "tags": tags,
                    "processing_time_ms": doc_result.get("processing_time_ms", 0),
                    "success": doc_result.get("success", False),
                    "error": doc_result.get("error")
                })

            return {
                "results": processed_results,
                "total_documents": result.get("total_documents", len(documents)),
                "successful": result.get("successful", 0),
                "failed": result.get("failed", 0)
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error in batch document tagging: {e.response.status_code}")
            return {
                "results": [{"doc_id": d.get("doc_id", "unknown"), "tags": [], "success": False, "error": str(e)} for d in documents],
                "successful": 0,
                "failed": len(documents)
            }
        except Exception as e:
            logger.error(f"Failed to batch tag documents: {e}", exc_info=True)
            return {
                "results": [{"doc_id": d.get("doc_id", "unknown"), "tags": [], "success": False, "error": str(e)} for d in documents],
                "successful": 0,
                "failed": len(documents)
            }

    # ========================================================================
    # Image Tagging
    # ========================================================================

    async def tag_image(
        self,
        image_embedding: List[float],
        image_bytes: bytes,
        clip_top_k: int = 15,
        clip_min_confidence: float = 0.15,
        owlvit_min_confidence: float = 0.15
    ) -> Dict[str, Any]:
        """
        Tag an image via the microservice.

        Args:
            image_embedding: Pre-computed CLIP embedding (512D)
            image_bytes: Raw image bytes
            clip_top_k: Number of CLIP candidates
            clip_min_confidence: CLIP confidence threshold
            owlvit_min_confidence: OWL-ViT confidence threshold

        Returns:
            Dict with 'verified_tags', 'candidate_tags', 'success', etc.
        """
        if not image_embedding or not image_bytes:
            logger.warning("Empty embedding or image provided for tagging")
            return {"verified_tags": [], "candidate_tags": [], "success": False, "error": "Empty input"}

        try:
            client = await self._get_client()

            # Encode image bytes to base64
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")

            response = await client.post(
                "/api/v1/tagging/tag-image",
                json={
                    "image_embedding": image_embedding,
                    "image_base64": image_base64,
                    "clip_top_k": clip_top_k,
                    "clip_min_confidence": clip_min_confidence,
                    "owlvit_min_confidence": owlvit_min_confidence
                }
            )
            response.raise_for_status()

            result = response.json()

            if result.get("success"):
                verified_tags = [
                    ImageTag(
                        label=t["label"],
                        confidence=t["confidence"],
                        bbox=t.get("bbox"),
                        verified=t.get("verified", True)
                    )
                    for t in result.get("verified_tags", [])
                ]
                candidate_tags = [
                    ImageTag(
                        label=t["label"],
                        confidence=t["confidence"],
                        verified=False
                    )
                    for t in result.get("candidate_tags", [])
                ]
                return {
                    "verified_tags": verified_tags,
                    "candidate_tags": candidate_tags,
                    "processing_time_ms": result.get("processing_time_ms", 0),
                    "success": True
                }
            else:
                logger.warning(f"Image tagging failed: {result.get('error')}")
                return {
                    "verified_tags": [],
                    "candidate_tags": [],
                    "success": False,
                    "error": result.get("error", "Unknown error")
                }

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error tagging image: {e.response.status_code}")
            return {"verified_tags": [], "candidate_tags": [], "success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Failed to tag image via microservice: {e}", exc_info=True)
            return {"verified_tags": [], "candidate_tags": [], "success": False, "error": str(e)}

    async def batch_tag_images(
        self,
        images: List[Dict[str, Any]],
        clip_top_k: int = 15,
        clip_min_confidence: float = 0.15,
        owlvit_min_confidence: float = 0.15,
        max_concurrent: int = 4
    ) -> Dict[str, Any]:
        """
        Tag multiple images via the microservice.

        Args:
            images: List of dicts with 'image_id', 'image_embedding', and 'image_bytes'
            clip_top_k: Number of CLIP candidates per image
            clip_min_confidence: CLIP confidence threshold
            owlvit_min_confidence: OWL-ViT confidence threshold
            max_concurrent: Maximum concurrent requests

        Returns:
            Dict with 'results' list and summary stats
        """
        if not images:
            return {"results": [], "successful": 0, "failed": 0}

        try:
            client = await self._get_client()

            # Encode all images to base64
            request_images = []
            for img in images:
                image_bytes = img.get("image_bytes", b"")
                request_images.append({
                    "image_id": img.get("image_id", "unknown"),
                    "image_embedding": img.get("image_embedding", []),
                    "image_base64": base64.b64encode(image_bytes).decode("utf-8") if image_bytes else ""
                })

            response = await client.post(
                "/api/v1/tagging/batch-tag-images",
                json={
                    "images": request_images,
                    "clip_top_k": clip_top_k,
                    "clip_min_confidence": clip_min_confidence,
                    "owlvit_min_confidence": owlvit_min_confidence,
                    "max_concurrent": max_concurrent
                },
                timeout=max(self.timeout, len(images) * 15)
            )
            response.raise_for_status()

            result = response.json()

            # Process results
            processed_results = []
            for img_result in result.get("results", []):
                verified_tags = [
                    ImageTag(
                        label=t["label"],
                        confidence=t["confidence"],
                        bbox=t.get("bbox"),
                        verified=True
                    )
                    for t in img_result.get("verified_tags", [])
                ]
                candidate_tags = [
                    ImageTag(
                        label=t["label"],
                        confidence=t["confidence"],
                        verified=False
                    )
                    for t in img_result.get("candidate_tags", [])
                ]
                processed_results.append({
                    "image_id": img_result["image_id"],
                    "verified_tags": verified_tags,
                    "candidate_tags": candidate_tags,
                    "processing_time_ms": img_result.get("processing_time_ms", 0),
                    "success": img_result.get("success", False),
                    "error": img_result.get("error")
                })

            return {
                "results": processed_results,
                "total_images": result.get("total_images", len(images)),
                "successful": result.get("successful", 0),
                "failed": result.get("failed", 0)
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error in batch image tagging: {e.response.status_code}")
            return {
                "results": [{"image_id": i.get("image_id", "unknown"), "verified_tags": [], "candidate_tags": [], "success": False, "error": str(e)} for i in images],
                "successful": 0,
                "failed": len(images)
            }
        except Exception as e:
            logger.error(f"Failed to batch tag images: {e}", exc_info=True)
            return {
                "results": [{"image_id": i.get("image_id", "unknown"), "verified_tags": [], "candidate_tags": [], "success": False, "error": str(e)} for i in images],
                "successful": 0,
                "failed": len(images)
            }

    async def health_check(self) -> dict:
        """
        Check the health of the tagging microservice.

        Returns:
            Health status dict
        """
        try:
            client = await self._get_client()
            response = await client.get("/health")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"status": "unreachable", "error": str(e)}


# Global client instance
_tagging_client: Optional[TaggingServiceClient] = None


def get_tagging_client() -> TaggingServiceClient:
    """Get the global tagging client instance."""
    global _tagging_client
    if _tagging_client is None:
        _tagging_client = TaggingServiceClient()
    return _tagging_client


# ============================================================================
# Backward-Compatible Wrapper Classes
# ============================================================================

class MicroserviceDocumentTagger:
    """
    Drop-in replacement for DocumentTagger that uses the microservice.
    Maintains the same interface for backward compatibility.
    """

    def __init__(self):
        """Initialize the microservice-backed document tagger."""
        self.client = get_tagging_client()
        logger.info("Initialized MicroserviceDocumentTagger")

    async def tag_document(
        self,
        text_content: str,
        filename: str = "",
        min_confidence: float = 0.5
    ) -> Dict[str, Any]:
        """Tag a document using the microservice."""
        return await self.client.tag_document(text_content, filename, min_confidence)

    async def store_document_tags(
        self,
        doc_id: str,
        user_id: str,
        tags: List[DocumentTag]
    ) -> int:
        """
        Store document-level tags in the database.
        Note: This still uses local Supabase client since storage is not in the microservice.
        """
        if not tags:
            logger.info(f"No tags to store for doc_id={doc_id}")
            return 0

        from core.deps import get_supabase
        supabase = get_supabase()

        # Prepare tag records
        tag_records = []
        for tag in tags:
            tag_records.append({
                "chunk_id": None,
                "doc_id": doc_id,
                "user_id": user_id,
                "tag_name": tag.tag_name,
                "confidence": tag.confidence,
                "verified": True,
                "bbox": None,
                "tag_type": "document",
                "category": tag.category,
                "reasoning": tag.reasoning
            })

        try:
            result = supabase.table("app_image_tags").insert(tag_records).execute()
            stored_count = len(result.data) if result.data else 0
            logger.info(f"Stored {stored_count} document tags for doc_id={doc_id}")
            return stored_count
        except Exception as e:
            logger.error(f"Failed to store document tags: {e}", exc_info=True)
            return 0


class MicroserviceImageTagger:
    """
    Drop-in replacement for image tagging that uses the microservice.
    """

    def __init__(self):
        """Initialize the microservice-backed image tagger."""
        self.client = get_tagging_client()
        logger.info("Initialized MicroserviceImageTagger")

    async def tag_image(
        self,
        chunk_id: str,
        image_embedding: List[float],
        image_bytes: bytes,
        user_id: str,
        doc_id: str,
        clip_min_confidence: float = 0.15,
        owlvit_min_confidence: float = 0.15,
        store_candidates: bool = False
    ) -> Dict[str, Any]:
        """
        Tag an image and store results in database.
        """
        import time
        start_time = time.time()

        # Call microservice
        result = await self.client.tag_image(
            image_embedding=image_embedding,
            image_bytes=image_bytes,
            clip_min_confidence=clip_min_confidence,
            owlvit_min_confidence=owlvit_min_confidence
        )

        if not result.get("success"):
            return {
                "chunk_id": chunk_id,
                "verified_tags": [],
                "candidate_tags": [],
                "processing_time_ms": (time.time() - start_time) * 1000,
                "error": result.get("error")
            }

        # Store tags in database
        await self._store_image_tags(
            chunk_id=chunk_id,
            doc_id=doc_id,
            user_id=user_id,
            verified_tags=result["verified_tags"],
            candidate_tags=result["candidate_tags"] if store_candidates else []
        )

        return {
            "chunk_id": chunk_id,
            "verified_tags": [{"label": t.label, "confidence": t.confidence, "bbox": t.bbox} for t in result["verified_tags"]],
            "candidate_tags": [{"label": t.label, "confidence": t.confidence} for t in result["candidate_tags"]],
            "processing_time_ms": result.get("processing_time_ms", 0)
        }

    async def _store_image_tags(
        self,
        chunk_id: str,
        doc_id: str,
        user_id: str,
        verified_tags: List[ImageTag],
        candidate_tags: List[ImageTag] = None
    ) -> None:
        """Store image tags in the database."""
        from core.deps import get_supabase
        supabase = get_supabase()

        tag_rows = []

        # Add verified tags
        for tag in verified_tags:
            tag_rows.append({
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "user_id": user_id,
                "tag_name": tag.label,
                "confidence": tag.confidence,
                "verified": True,
                "bbox": tag.bbox
            })

        # Optionally add unverified candidates
        if candidate_tags:
            verified_labels = {t.label for t in verified_tags}
            for tag in candidate_tags:
                if tag.label not in verified_labels:
                    tag_rows.append({
                        "chunk_id": chunk_id,
                        "doc_id": doc_id,
                        "user_id": user_id,
                        "tag_name": tag.label,
                        "confidence": tag.confidence,
                        "verified": False,
                        "bbox": None
                    })

        if tag_rows:
            supabase.table("app_image_tags").insert(tag_rows).execute()
