"""Audit and cleanup endpoints."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client
from pydantic import BaseModel

from core import get_current_user, AuthUser
from core.deps import get_supabase, get_ragie_service
from services.ragie_service import RagieService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/audit", tags=["audit"])


class OrphanedDocInfo(BaseModel):
    """Info about an orphaned document."""
    ragie_id: str
    reason: str  # "missing_in_db" or "missing_in_ragie"
    filename: str | None = None


class AuditResponse(BaseModel):
    """Audit results."""
    ragie_total: int
    db_total: int
    orphaned: list[OrphanedDocInfo]
    status: str


@router.get("/orphaned-documents", response_model=AuditResponse)
async def check_orphaned_documents(
    current_user: AuthUser = Depends(get_current_user),
    ragie_service: RagieService = Depends(get_ragie_service),
    supabase: Client = Depends(get_supabase),
):
    """Check for orphaned documents in Ragie vs Supabase."""
    try:
        # Get all documents in Supabase for this user
        db_response = supabase.table("ragie_documents").select(
            "ragie_document_id, filename"
        ).eq("user_id", current_user.id).execute()

        db_docs = {doc["ragie_document_id"]: doc for doc in (db_response.data or [])}

        # Get all documents in Ragie for this user
        # Since we filter by metadata, we need to get docs and filter client-side
        try:
            ragie_response = await ragie_service.retrieve(
                query="*",
                user_id=current_user.id,
                top_k=1000  # Get a lot to find all docs
            )
            ragie_doc_ids = set()
            if ragie_response.scored_chunks:
                for chunk in ragie_response.scored_chunks:
                    if chunk.document_id:
                        ragie_doc_ids.add(chunk.document_id)
        except Exception as e:
            logger.warning(f"Could not retrieve all docs from Ragie: {e}")
            ragie_doc_ids = set()

        orphaned = []

        # Find docs in DB but not in Ragie
        for db_id, db_doc in db_docs.items():
            if db_id not in ragie_doc_ids:
                orphaned.append(OrphanedDocInfo(
                    ragie_id=db_id,
                    reason="missing_in_ragie",
                    filename=db_doc.get("filename")
                ))

        # Find docs in Ragie but not in DB
        for ragie_id in ragie_doc_ids:
            if ragie_id not in db_docs:
                orphaned.append(OrphanedDocInfo(
                    ragie_id=ragie_id,
                    reason="missing_in_db",
                    filename=None
                ))

        status = "clean" if not orphaned else "has_orphaned"

        return AuditResponse(
            ragie_total=len(ragie_doc_ids),
            db_total=len(db_docs),
            orphaned=orphaned,
            status=status
        )

    except Exception as e:
        logger.error(f"Error auditing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cleanup-orphaned")
async def cleanup_orphaned_documents(
    current_user: AuthUser = Depends(get_current_user),
    ragie_service: RagieService = Depends(get_ragie_service),
    supabase: Client = Depends(get_supabase),
):
    """Remove orphaned database records (docs missing in Ragie)."""
    try:
        # Get all documents in Supabase for this user
        db_response = supabase.table("ragie_documents").select(
            "id, ragie_document_id, filename"
        ).eq("user_id", current_user.id).execute()

        db_docs = {doc["ragie_document_id"]: doc for doc in (db_response.data or [])}

        # Get all documents in Ragie for this user
        try:
            ragie_response = await ragie_service.retrieve(
                query="*",
                user_id=current_user.id,
                top_k=1000
            )
            ragie_doc_ids = set()
            if ragie_response.scored_chunks:
                for chunk in ragie_response.scored_chunks:
                    if chunk.document_id:
                        ragie_doc_ids.add(chunk.document_id)
        except Exception as e:
            logger.warning(f"Could not retrieve all docs from Ragie: {e}")
            ragie_doc_ids = set()

        cleaned = []

        # Delete from DB any docs not in Ragie
        for ragie_id, db_doc in db_docs.items():
            if ragie_id not in ragie_doc_ids:
                supabase.table("ragie_documents").delete().eq("id", db_doc["id"]).execute()
                cleaned.append({
                    "id": db_doc["id"],
                    "ragie_id": ragie_id,
                    "filename": db_doc["filename"]
                })

        return {
            "message": f"Cleaned up {len(cleaned)} orphaned database records",
            "cleaned": cleaned
        }

    except Exception as e:
        logger.error(f"Error cleaning up orphaned documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))
