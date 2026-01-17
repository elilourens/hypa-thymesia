"""
Chunk formatting endpoints for manual formatting operations.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.security import get_current_user, AuthUser
from core.deps import get_supabase, get_pinecone
from formatting.batch_formatter import BatchChunkFormatter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/formatting", tags=["formatting"])


class FormatDocumentRequest(BaseModel):
    """Request to format all chunks for a document."""
    doc_id: str
    max_chunks: Optional[int] = 1000


class FormatDocumentResponse(BaseModel):
    """Response from formatting operation."""
    doc_id: str
    total_chunks: int
    formatted: int
    failed: int
    skipped: int
    errors: list[str]


@router.post("/format-document", response_model=FormatDocumentResponse)
async def format_document_chunks(
    req: FormatDocumentRequest,
    auth: AuthUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
    pinecone=Depends(get_pinecone),
):
    """
    Manually trigger formatting for all text chunks in a document.

    This endpoint allows you to format existing documents that were
    uploaded before the automatic formatting feature was enabled.

    Args:
        req: Format request with doc_id and optional max_chunks
        auth: Authenticated user
        supabase: Supabase client
        pinecone: Pinecone client

    Returns:
        Formatting results with counts and any errors
    """
    user_id = auth.id

    logger.info(f"Manual formatting request for doc_id={req.doc_id}, user_id={user_id}")

    try:
        # Create formatter
        formatter = BatchChunkFormatter(
            supabase=supabase,
            pinecone_client=pinecone
        )

        # Format chunks
        result = await formatter.format_document_chunks(
            doc_id=req.doc_id,
            user_id=user_id,
            max_chunks=req.max_chunks
        )

        logger.info(
            f"Manual formatting complete for doc_id={req.doc_id}: "
            f"{result['formatted']} formatted, {result['failed']} failed"
        )

        return FormatDocumentResponse(**result)

    except Exception as e:
        logger.error(f"Manual formatting failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Formatting failed: {str(e)}"
        )


class BatchFormatRequest(BaseModel):
    """Request to format multiple documents."""
    group_id: Optional[str] = None
    max_documents: Optional[int] = 10
    max_chunks_per_doc: Optional[int] = 1000
    only_unformatted: bool = True


class BatchFormatResponse(BaseModel):
    """Response from batch formatting operation."""
    documents_processed: int
    total_formatted: int
    total_failed: int
    total_skipped: int
    document_results: list[FormatDocumentResponse]


@router.post("/batch-format", response_model=BatchFormatResponse)
async def batch_format_documents(
    req: BatchFormatRequest,
    auth: AuthUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
    pinecone=Depends(get_pinecone),
):
    """
    Format multiple documents in batch.

    Useful for reformatting existing documents that were uploaded
    before automatic formatting was enabled.

    Args:
        req: Batch format request
        auth: Authenticated user
        supabase: Supabase client
        pinecone: Pinecone client

    Returns:
        Batch formatting results
    """
    user_id = auth.id

    logger.info(
        f"Batch formatting request: group_id={req.group_id}, "
        f"max_docs={req.max_documents}, user_id={user_id}"
    )

    try:
        # Build query to find documents with unformatted chunks
        query = supabase.table("app_chunks").select(
            "doc_id"
        ).eq("user_id", user_id).eq("modality", "text")

        if req.only_unformatted:
            query = query.neq("formatting_status", "formatted")

        if req.group_id:
            # Join with app_doc_meta to filter by group
            query = query.eq("group_id", req.group_id)

        # Get distinct doc_ids
        result = query.limit(req.max_documents).execute()

        if not result.data:
            logger.info("No documents found to format")
            return BatchFormatResponse(
                documents_processed=0,
                total_formatted=0,
                total_failed=0,
                total_skipped=0,
                document_results=[]
            )

        # Get unique doc_ids
        doc_ids = list(set(chunk["doc_id"] for chunk in result.data))
        logger.info(f"Found {len(doc_ids)} documents to format")

        # Create formatter
        formatter = BatchChunkFormatter(
            supabase=supabase,
            pinecone_client=pinecone
        )

        # Format each document
        document_results = []
        total_formatted = 0
        total_failed = 0
        total_skipped = 0

        for doc_id in doc_ids:
            try:
                doc_result = await formatter.format_document_chunks(
                    doc_id=doc_id,
                    user_id=user_id,
                    max_chunks=req.max_chunks_per_doc
                )

                document_results.append(FormatDocumentResponse(**doc_result))
                total_formatted += doc_result["formatted"]
                total_failed += doc_result["failed"]
                total_skipped += doc_result["skipped"]

                logger.info(f"Formatted doc {doc_id}: {doc_result['formatted']} chunks")

            except Exception as e:
                logger.error(f"Failed to format doc {doc_id}: {e}")
                document_results.append(FormatDocumentResponse(
                    doc_id=doc_id,
                    total_chunks=0,
                    formatted=0,
                    failed=0,
                    skipped=0,
                    errors=[str(e)]
                ))

        logger.info(
            f"Batch formatting complete: {len(doc_ids)} documents, "
            f"{total_formatted} formatted, {total_failed} failed"
        )

        return BatchFormatResponse(
            documents_processed=len(doc_ids),
            total_formatted=total_formatted,
            total_failed=total_failed,
            total_skipped=total_skipped,
            document_results=document_results
        )

    except Exception as e:
        logger.error(f"Batch formatting failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Batch formatting failed: {str(e)}"
        )


class FormattingStatsResponse(BaseModel):
    """Statistics about chunk formatting status."""
    total_text_chunks: int
    formatted_chunks: int
    unformatted_chunks: int
    formatting_in_progress: int
    failed_chunks: int
    formatting_percentage: float


@router.get("/stats", response_model=FormattingStatsResponse)
async def get_formatting_stats(
    auth: AuthUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    """
    Get statistics about chunk formatting status for the current user.

    Returns counts and percentages of formatted vs unformatted chunks.
    """
    user_id = auth.id

    try:
        # Get all text chunks for user
        total_result = supabase.table("app_chunks").select(
            "chunk_id", count="exact"
        ).eq("user_id", user_id).eq("modality", "text").execute()

        total_chunks = total_result.count or 0

        if total_chunks == 0:
            return FormattingStatsResponse(
                total_text_chunks=0,
                formatted_chunks=0,
                unformatted_chunks=0,
                formatting_in_progress=0,
                failed_chunks=0,
                formatting_percentage=0.0
            )

        # Count by status
        formatted_result = supabase.table("app_chunks").select(
            "chunk_id", count="exact"
        ).eq("user_id", user_id).eq("modality", "text").eq(
            "formatting_status", "formatted"
        ).execute()

        formatting_result = supabase.table("app_chunks").select(
            "chunk_id", count="exact"
        ).eq("user_id", user_id).eq("modality", "text").eq(
            "formatting_status", "formatting"
        ).execute()

        failed_result = supabase.table("app_chunks").select(
            "chunk_id", count="exact"
        ).eq("user_id", user_id).eq("modality", "text").eq(
            "formatting_status", "failed"
        ).execute()

        formatted_chunks = formatted_result.count or 0
        formatting_in_progress = formatting_result.count or 0
        failed_chunks = failed_result.count or 0
        unformatted_chunks = total_chunks - formatted_chunks - formatting_in_progress - failed_chunks

        percentage = (formatted_chunks / total_chunks * 100) if total_chunks > 0 else 0.0

        return FormattingStatsResponse(
            total_text_chunks=total_chunks,
            formatted_chunks=formatted_chunks,
            unformatted_chunks=unformatted_chunks,
            formatting_in_progress=formatting_in_progress,
            failed_chunks=failed_chunks,
            formatting_percentage=round(percentage, 2)
        )

    except Exception as e:
        logger.error(f"Failed to get formatting stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get stats: {str(e)}"
        )
