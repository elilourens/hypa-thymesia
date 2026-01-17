"""
HTTP client for the Formatting Microservice.
Replaces direct Ollama calls with HTTP calls to the microservice.
"""

import asyncio
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class FormattingServiceClient:
    """HTTP client for communicating with the formatting microservice."""

    def __init__(
        self,
        base_url: str = None,
        timeout: int = 60
    ):
        """
        Initialize the formatting service client.

        Args:
            base_url: Base URL of the formatting microservice
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or os.getenv(
            "FORMATTING_SERVICE_URL",
            "http://localhost:8002"
        )
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

        logger.info(f"Initialized FormattingServiceClient with base_url={self.base_url}")

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

    async def format_chunk(self, text: str) -> Optional[str]:
        """
        Format a single text chunk via the microservice.

        Args:
            text: Raw text chunk to format

        Returns:
            Formatted text or None if formatting failed
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for formatting")
            return None

        try:
            client = await self._get_client()

            response = await client.post(
                "/api/v1/formatting/format-chunk",
                json={"text": text}
            )
            response.raise_for_status()

            result = response.json()

            if result.get("success"):
                return result.get("formatted_text")
            else:
                logger.warning(f"Formatting failed: {result.get('error')}")
                return None

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error formatting chunk: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Failed to format chunk via microservice: {e}", exc_info=True)
            return None

    async def batch_format_chunks(
        self,
        chunks: list[dict],
        max_concurrent: int = 10
    ) -> dict:
        """
        Format multiple chunks via the microservice.

        Args:
            chunks: List of dicts with 'chunk_id' and 'text' fields
            max_concurrent: Maximum concurrent requests (passed to microservice)

        Returns:
            Dict with 'formatted' and 'failed' lists of (chunk_id, text/error) tuples
        """
        if not chunks:
            return {"formatted": [], "failed": []}

        try:
            client = await self._get_client()

            response = await client.post(
                "/api/v1/formatting/batch-format",
                json={
                    "chunks": chunks,
                    "max_concurrent": max_concurrent
                },
                timeout=max(self.timeout, len(chunks) * 5)  # Scale timeout with chunk count
            )
            response.raise_for_status()

            result = response.json()

            formatted = []
            failed = []

            for chunk_result in result.get("results", []):
                if chunk_result.get("success"):
                    formatted.append((
                        chunk_result["chunk_id"],
                        chunk_result["formatted_text"]
                    ))
                else:
                    failed.append((
                        chunk_result["chunk_id"],
                        chunk_result.get("error", "Unknown error")
                    ))

            logger.info(f"Batch formatting: {len(formatted)} formatted, {len(failed)} failed")
            return {"formatted": formatted, "failed": failed}

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error in batch formatting: {e.response.status_code}")
            # Return all chunks as failed
            return {
                "formatted": [],
                "failed": [(c.get("chunk_id", "unknown"), str(e)) for c in chunks]
            }
        except Exception as e:
            logger.error(f"Failed to batch format via microservice: {e}", exc_info=True)
            return {
                "formatted": [],
                "failed": [(c.get("chunk_id", "unknown"), str(e)) for c in chunks]
            }

    async def health_check(self) -> dict:
        """
        Check the health of the formatting microservice.

        Returns:
            Health status dict
        """
        try:
            client = await self._get_client()

            response = await client.get("/api/v1/formatting/health")
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unreachable",
                "ollama_connected": False,
                "error": str(e)
            }


# Global client instance
_formatting_client: Optional[FormattingServiceClient] = None


def get_formatting_client() -> FormattingServiceClient:
    """Get the global formatting client instance."""
    global _formatting_client
    if _formatting_client is None:
        _formatting_client = FormattingServiceClient()
    return _formatting_client


class MicroserviceOllamaFormatter:
    """
    Drop-in replacement for OllamaFormatter that uses the microservice.
    Maintains the same interface for backward compatibility.
    """

    def __init__(self):
        """Initialize the microservice-backed formatter."""
        self.client = get_formatting_client()
        logger.info("Initialized MicroserviceOllamaFormatter")

    def format_chunk(self, text: str) -> Optional[str]:
        """
        Format a single text chunk (sync wrapper for async call).

        Args:
            text: Raw text chunk to format

        Returns:
            Formatted text or None if formatting failed
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a new task in the running loop
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.client.format_chunk(text)
                    )
                    return future.result(timeout=60)
            else:
                return loop.run_until_complete(self.client.format_chunk(text))
        except Exception as e:
            logger.error(f"Failed to format chunk: {e}", exc_info=True)
            return None

    async def format_chunk_async(self, text: str) -> Optional[str]:
        """
        Format a single text chunk asynchronously.

        Args:
            text: Raw text chunk to format

        Returns:
            Formatted text or None if formatting failed
        """
        return await self.client.format_chunk(text)
