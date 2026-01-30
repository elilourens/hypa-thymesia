"""
Formatting API endpoints for the microservice.
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.schemas.formatting import (
    FormatChunkRequest,
    FormatChunkResponse,
    BatchFormatRequest,
    BatchFormatResponse,
    ChunkResult,
    HealthResponse
)
from app.services.ollama_formatter import OllamaFormatter, get_formatter
from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/formatting", tags=["formatting"])


@router.post("/format-chunk", response_model=FormatChunkResponse)
async def format_single_chunk(req: FormatChunkRequest):
    """
    Format a single text chunk using Ollama.

    Args:
        req: Request containing the text to format

    Returns:
        Formatted text result
    """
    logger.info(f"Formatting single chunk of length {len(req.text)}")

    try:
        formatter = get_formatter()

        # Run formatting in executor to not block event loop
        loop = asyncio.get_event_loop()
        formatted_text = await loop.run_in_executor(
            None, formatter.format_chunk, req.text
        )

        if formatted_text:
            logger.info(f"Successfully formatted chunk ({len(formatted_text)} chars)")
            return FormatChunkResponse(
                original_text=req.text,
                formatted_text=formatted_text,
                success=True
            )
        else:
            logger.warning("Formatter returned None")
            return FormatChunkResponse(
                original_text=req.text,
                formatted_text=None,
                success=False,
                error="Formatter returned empty result"
            )

    except Exception as e:
        logger.error(f"Failed to format chunk: {e}", exc_info=True)
        return FormatChunkResponse(
            original_text=req.text,
            formatted_text=None,
            success=False,
            error=str(e)
        )


@router.post("/batch-format", response_model=BatchFormatResponse)
async def batch_format_chunks(req: BatchFormatRequest):
    """
    Format multiple text chunks concurrently.

    Args:
        req: Request containing list of chunks with chunk_id and text

    Returns:
        Batch formatting results
    """
    logger.info(f"Batch formatting {len(req.chunks)} chunks")

    settings = get_settings()
    max_concurrent = req.max_concurrent or settings.OLLAMA_NUM_PARALLEL

    formatter = get_formatter()
    semaphore = asyncio.Semaphore(max_concurrent)

    async def format_single(chunk_data: dict) -> ChunkResult:
        """Format a single chunk with semaphore limiting."""
        chunk_id = chunk_data.get("chunk_id", "unknown")
        text = chunk_data.get("text", "")

        if not text:
            return ChunkResult(
                chunk_id=chunk_id,
                original_text=text,
                formatted_text=None,
                success=False,
                error="Empty text provided"
            )

        async with semaphore:
            try:
                loop = asyncio.get_event_loop()
                formatted_text = await loop.run_in_executor(
                    None, formatter.format_chunk, text
                )

                if formatted_text:
                    return ChunkResult(
                        chunk_id=chunk_id,
                        original_text=text,
                        formatted_text=formatted_text,
                        success=True
                    )
                else:
                    return ChunkResult(
                        chunk_id=chunk_id,
                        original_text=text,
                        formatted_text=None,
                        success=False,
                        error="Formatter returned empty result"
                    )

            except Exception as e:
                logger.error(f"Failed to format chunk {chunk_id}: {e}")
                return ChunkResult(
                    chunk_id=chunk_id,
                    original_text=text,
                    formatted_text=None,
                    success=False,
                    error=str(e)
                )

    # Execute all formatting tasks concurrently
    results = await asyncio.gather(*[
        format_single(chunk) for chunk in req.chunks
    ])

    formatted_count = sum(1 for r in results if r.success)
    failed_count = len(results) - formatted_count

    logger.info(f"Batch formatting complete: {formatted_count} formatted, {failed_count} failed")

    return BatchFormatResponse(
        total_chunks=len(results),
        formatted=formatted_count,
        failed=failed_count,
        results=results
    )


@router.get("/health", response_model=HealthResponse)
async def check_health():
    """
    Check the health of the formatting service and Ollama connection.

    Returns:
        Health status including Ollama connectivity
    """
    settings = get_settings()

    try:
        # Try to create a formatter and check Ollama connection
        formatter = OllamaFormatter()

        # Try a simple test to verify Ollama is reachable
        # Using list models endpoint as a health check
        formatter.client.list()

        return HealthResponse(
            status="healthy",
            ollama_connected=True,
            ollama_model=settings.OLLAMA_MODEL
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            ollama_connected=False,
            ollama_model=settings.OLLAMA_MODEL,
            error=str(e)
        )
