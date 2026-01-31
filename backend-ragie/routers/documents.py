"""Document management endpoints."""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from supabase import Client

from core import get_current_user, AuthUser
from core.deps import get_supabase, get_supabase_admin, get_ragie_service
from core.rate_limiting import rate_limit
from core.user_limits import check_user_can_upload, get_user_quota_status, add_to_user_monthly_throughput, add_to_user_monthly_file_count
from services.ragie_service import RagieService
from services.video_service import VideoService
from schemas import DocumentResponse, DocumentListResponse, DocumentDeleteResponse, DocumentStatusResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


def get_video_service(current_user: AuthUser = Depends(get_current_user), supabase: Client = Depends(get_supabase_admin), ragie_service: RagieService = Depends(get_ragie_service)) -> VideoService:
    """Dependency to get video service (uses admin client to bypass RLS for write operations)."""
    return VideoService(supabase, ragie_service)


@router.post("/upload", response_model=DocumentResponse)
@rate_limit(calls_per_minute=10)
async def upload_document(
    file: UploadFile = File(...),
    group_id: Optional[str] = Query(None),
    current_user: AuthUser = Depends(get_current_user),
    ragie_service: RagieService = Depends(get_ragie_service),
    supabase: Client = Depends(get_supabase),
):
    """Upload a document to Ragie."""
    try:
        # Get file size before upload
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        # Check user quota with file size
        try:
            check_user_can_upload(supabase, current_user.id, file_size_bytes=file_size)
        except HTTPException:
            raise

        # Upload to Ragie
        ragie_response = await ragie_service.upload_document(
            file=file,
            user_id=current_user.id,
            group_id=group_id,
            metadata={"mime_type": file.content_type}
        )

        # Create database record
        doc_record = supabase.table("ragie_documents").insert({
            "user_id": current_user.id,
            "group_id": group_id,
            "ragie_document_id": str(ragie_response.id),
            "filename": file.filename,
            "mime_type": file.content_type,
            "file_size_bytes": file_size,
            "status": ragie_response.status,
            "ragie_metadata": {
                "user_id": current_user.id,
                "group_id": group_id,
                "mime_type": file.content_type
            }
        }).execute()

        if not doc_record.data:
            raise HTTPException(status_code=500, detail="Failed to create document record")

        doc = doc_record.data[0]

        # Track upload throughput and file count
        add_to_user_monthly_throughput(supabase, current_user.id, file_size)
        add_to_user_monthly_file_count(supabase, current_user.id)

        # Fetch group name if document has a group
        group_name = None
        if doc.get("group_id"):
            group_response = supabase.table("app_groups").select("name").eq(
                "group_id", doc["group_id"]
            ).eq("user_id", current_user.id).single().execute()
            if group_response.data:
                group_name = group_response.data.get("name")

        return DocumentResponse(
            id=doc["id"],
            ragie_document_id=doc["ragie_document_id"],
            filename=doc["filename"],
            mime_type=doc["mime_type"],
            file_size_bytes=doc["file_size_bytes"],
            status=doc["status"],
            group_id=doc["group_id"],
            group_name=group_name,
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading document: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload document")


@router.get("/list", response_model=DocumentListResponse)
@rate_limit(calls_per_minute=10)
async def list_documents(
    group_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("created_at", regex="^(created_at|filename|page_count)$"),
    dir: str = Query("desc", regex="^(asc|desc)$"),
    search: Optional[str] = Query(None),
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """List user's documents with filtering, sorting, and pagination."""
    try:
        # Start with base query
        query = supabase.table("ragie_documents").select(
            "*"
        ).eq("user_id", current_user.id)

        if group_id:
            query = query.eq("group_id", group_id)

        # If search is applied, we need to fetch all docs for client-side filtering
        # Otherwise, use database pagination
        if search:
            # Fetch all matching documents for search filtering
            response = query.execute()
            all_docs = response.data or []

            # Apply search filter (case-insensitive)
            search_lower = search.lower()
            all_docs = [doc for doc in all_docs if search_lower in doc["filename"].lower()]

            # Sort results
            desc = dir == "desc"
            if sort == "created_at":
                all_docs.sort(key=lambda x: x["created_at"], reverse=desc)
            elif sort == "filename":
                all_docs.sort(key=lambda x: x["filename"].lower(), reverse=desc)
            elif sort == "page_count":
                all_docs.sort(key=lambda x: x.get("page_count") or 0, reverse=desc)

            total_count = len(all_docs)
            offset = (page - 1) * page_size
            paginated_docs = all_docs[offset:offset + page_size]
        else:
            # Use database-level pagination for better performance
            desc = dir == "desc"
            if sort == "created_at":
                query = query.order("created_at", desc=desc)
            elif sort == "filename":
                query = query.order("filename", desc=desc)
            elif sort == "page_count":
                query = query.order("page_count", desc=desc)

            # Apply pagination (note: Supabase doesn't support count with range in single query)
            # So we first get count, then fetch page
            offset = (page - 1) * page_size

            # Get paginated results
            response = query.range(offset, offset + page_size - 1).execute()
            paginated_docs = response.data or []

            # Get total count for this query (all matching docs, not just this page)
            count_response = supabase.table("ragie_documents").select(
                "*"
            ).eq("user_id", current_user.id)
            if group_id:
                count_response = count_response.eq("group_id", group_id)
            count_response = count_response.execute()
            total_count = len(count_response.data or [])

        # Fetch group names for documents with group_id
        group_names = {}
        group_ids = {doc.get("group_id") for doc in paginated_docs if doc.get("group_id")}
        if group_ids:
            groups_response = supabase.table("app_groups").select("group_id, name").eq(
                "user_id", current_user.id
            ).execute()
            group_names = {g["group_id"]: g["name"] for g in (groups_response.data or [])}

        documents = [
            DocumentResponse(
                id=doc["id"],
                ragie_document_id=doc["ragie_document_id"],
                filename=doc["filename"],
                mime_type=doc["mime_type"],
                file_size_bytes=doc["file_size_bytes"],
                status=doc["status"],
                chunk_count=doc["chunk_count"],
                page_count=doc["page_count"],
                group_id=doc["group_id"],
                group_name=group_names.get(doc.get("group_id")) if doc.get("group_id") else None,
                created_at=doc["created_at"],
                updated_at=doc["updated_at"],
            )
            for doc in paginated_docs
        ]

        # Calculate if there are more items
        has_more = (offset + page_size) < total_count

        return DocumentListResponse(
            items=documents,
            total=total_count,
            has_more=has_more,
        )

    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail="Failed to list documents")


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str,
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Get a specific document."""
    try:
        response = supabase.table("ragie_documents").select(
            "*"
        ).eq("id", doc_id).eq("user_id", current_user.id).single().execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Document not found")

        doc = response.data

        # Fetch group name if document has a group
        group_name = None
        if doc.get("group_id"):
            group_response = supabase.table("app_groups").select("name").eq(
                "group_id", doc["group_id"]
            ).eq("user_id", current_user.id).single().execute()
            if group_response.data:
                group_name = group_response.data.get("name")

        return DocumentResponse(
            id=doc["id"],
            ragie_document_id=doc["ragie_document_id"],
            filename=doc["filename"],
            mime_type=doc["mime_type"],
            file_size_bytes=doc["file_size_bytes"],
            status=doc["status"],
            chunk_count=doc["chunk_count"],
            page_count=doc["page_count"],
            group_id=doc["group_id"],
            group_name=group_name,
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve document")


@router.delete("/{doc_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    doc_id: str,
    current_user: AuthUser = Depends(get_current_user),
    ragie_service: RagieService = Depends(get_ragie_service),
    supabase: Client = Depends(get_supabase),
    video_service: VideoService = Depends(get_video_service),
):
    """Delete a document."""
    try:
        # Get document from database
        response = supabase.table("ragie_documents").select(
            "*"
        ).eq("id", doc_id).eq("user_id", current_user.id).single().execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Document not found")

        doc = response.data

        # Check if this is a video document (has storage_bucket field)
        if doc.get("storage_bucket"):
            # Use VideoService for video deletion (handles storage cleanup)
            await video_service.delete_document(doc_id, current_user.id)
        else:
            # Regular document deletion
            # Delete from Ragie
            if doc.get("ragie_document_id"):
                try:
                    await ragie_service.delete_document(doc["ragie_document_id"])
                except Exception as e:
                    logger.warning(f"Failed to delete from Ragie: {e}")
                    # Continue with database deletion anyway

            # Delete from database
            supabase.table("ragie_documents").delete().eq("id", doc_id).execute()

        return DocumentDeleteResponse(
            message="Document deleted successfully",
            document_id=doc_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete document")


@router.patch("/{doc_id}", response_model=DocumentResponse)
async def update_document(
    doc_id: str,
    group_id: Optional[str] = Query(None),
    current_user: AuthUser = Depends(get_current_user),
    ragie_service: RagieService = Depends(get_ragie_service),
    supabase: Client = Depends(get_supabase),
):
    """Update a document's group."""
    try:
        # Get document from database
        response = supabase.table("ragie_documents").select(
            "*"
        ).eq("id", doc_id).eq("user_id", current_user.id).single().execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Document not found")

        doc = response.data

        # Update metadata in Ragie
        if doc.get("ragie_document_id"):
            try:
                await ragie_service.update_metadata(
                    doc["ragie_document_id"],
                    {"group_id": group_id}
                )
            except Exception as e:
                logger.warning(f"Failed to update Ragie metadata: {e}")
                # Continue with database update even if Ragie sync fails

        # Update document group in database
        ragie_metadata = doc.get("ragie_metadata", {}) or {}
        ragie_metadata["group_id"] = group_id

        update_data = {
            "group_id": group_id,
            "ragie_metadata": ragie_metadata
        }
        supabase.table("ragie_documents").update(update_data).eq("id", doc_id).execute()

        # Fetch group name if document has a group
        group_name = None
        if group_id:
            group_response = supabase.table("app_groups").select("name").eq(
                "group_id", group_id
            ).eq("user_id", current_user.id).single().execute()
            if group_response.data:
                group_name = group_response.data.get("name")

        return DocumentResponse(
            id=doc["id"],
            ragie_document_id=doc["ragie_document_id"],
            filename=doc["filename"],
            mime_type=doc["mime_type"],
            file_size_bytes=doc["file_size_bytes"],
            status=doc["status"],
            chunk_count=doc["chunk_count"],
            page_count=doc["page_count"],
            group_id=group_id,
            group_name=group_name,
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating document: {e}")
        raise HTTPException(status_code=500, detail="Failed to update document")


@router.get("/{doc_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    doc_id: str,
    current_user: AuthUser = Depends(get_current_user),
    ragie_service: RagieService = Depends(get_ragie_service),
    supabase: Client = Depends(get_supabase),
):
    """Get document processing status."""
    try:
        # Get from database
        response = supabase.table("ragie_documents").select(
            "*"
        ).eq("id", doc_id).eq("user_id", current_user.id).single().execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Document not found")

        doc = response.data

        # Get latest status from Ragie
        if doc.get("ragie_document_id"):
            try:
                ragie_doc = await ragie_service.get_document_status(doc["ragie_document_id"])

                # Update database if status changed
                if ragie_doc.status != doc["status"]:
                    update_data = {
                        "status": ragie_doc.status,
                    }
                    if hasattr(ragie_doc, "chunk_count") and ragie_doc.chunk_count:
                        update_data["chunk_count"] = int(ragie_doc.chunk_count)
                    if hasattr(ragie_doc, "page_count") and ragie_doc.page_count:
                        update_data["page_count"] = int(ragie_doc.page_count)

                    supabase.table("ragie_documents").update(update_data).eq("id", doc_id).execute()

                    # Update local doc object with changes instead of fetching again
                    doc.update(update_data)

            except Exception as e:
                logger.warning(f"Failed to get status from Ragie: {e}")

        return DocumentStatusResponse(
            id=doc["id"],
            ragie_document_id=doc["ragie_document_id"],
            filename=doc["filename"],
            status=doc["status"],
            chunk_count=doc["chunk_count"],
            page_count=doc["page_count"],
            updated_at=doc["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get document status")
