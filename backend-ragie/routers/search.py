"""Search and retrieval endpoints."""

import logging
from fastapi import APIRouter, Depends, HTTPException

from core import get_current_user, AuthUser
from core.deps import get_ragie_service
from services.ragie_service import RagieService
from schemas import SearchRequest, SearchResponse, ScoredChunk

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"])


@router.post("/retrieve", response_model=SearchResponse)
async def retrieve(
    request: SearchRequest,
    current_user: AuthUser = Depends(get_current_user),
    ragie_service: RagieService = Depends(get_ragie_service),
):
    """Retrieve document chunks using semantic search."""
    try:
        # Query Ragie
        results = await ragie_service.retrieve(
            query=request.query,
            user_id=current_user.id,
            top_k=request.top_k or 8,
            rerank=request.rerank if request.rerank is not None else True,
            group_id=request.group_id,
            max_chunks_per_document=request.max_chunks_per_document or 0,
            modality=request.modality,
        )

        # Format response
        scored_chunks = []
        if hasattr(results, "scored_chunks") and results.scored_chunks:
            for chunk in results.scored_chunks:
                metadata = chunk.metadata if hasattr(chunk, "metadata") else {}
                if isinstance(metadata, dict):
                    metadata = dict(metadata)  # Make a copy
                else:
                    metadata = {}

                # Extract filename from text if it's on the first line
                text = chunk.text if hasattr(chunk, "text") else ""
                if text and not metadata.get("title"):
                    first_line = text.split("\n")[0].strip()
                    # If first line looks like a filename (has a dot), use it as title
                    if first_line and "." in first_line and len(first_line) < 255:
                        metadata["title"] = first_line

                # Enrich metadata with storage info for Ragie-stored documents
                # Ragie documents are accessed via our proxy endpoint or Supabase storage
                doc_id = chunk.document_id if hasattr(chunk, "document_id") else None
                if doc_id:
                    # Check if this is a video document stored in Supabase
                    is_video = metadata.get("chunk_content_type") == "video"
                    logger.info(f"Chunk {doc_id}: chunk_content_type={metadata.get('chunk_content_type')}, is_video={is_video}")

                    if is_video:
                        # Video chunks: get storage path and thumbnail from Supabase
                        try:
                            from core.deps import get_supabase
                            supabase = get_supabase()

                            # Get video document info
                            video_response = supabase.table("ragie_documents").select(
                                "id, storage_path, storage_bucket"
                            ).eq("ragie_document_id", str(doc_id)).single().execute()

                            if video_response.data:
                                metadata["bucket"] = video_response.data.get("storage_bucket", "videos")
                                metadata["storage_path"] = video_response.data["storage_path"]

                                # Thumbnail is stored in videos bucket under thumbnails/{ragie_documents.id}.jpg
                                supabase_doc_id = video_response.data.get("id")
                                metadata["thumbnail_url"] = f"thumbnails/{supabase_doc_id}.jpg"
                                logger.info(f"Set thumbnail_url for document {doc_id}: {metadata['thumbnail_url']}")
                            else:
                                # Fallback to Ragie if not found in Supabase
                                metadata["bucket"] = "ragie"
                                metadata["storage_path"] = str(doc_id)
                        except Exception:
                            # Fallback to Ragie on error
                            metadata["bucket"] = "ragie"
                            metadata["storage_path"] = str(doc_id)
                    else:
                        # Non-video documents: use Ragie storage
                        metadata["bucket"] = "ragie"
                        metadata["storage_path"] = str(doc_id)

                    # Infer modality from content type if not already set
                    if "modality" not in metadata:
                        # Try mime_type first
                        if "mime_type" in metadata:
                            mime_type = metadata.get("mime_type", "").lower()
                            if mime_type.startswith("image/"):
                                metadata["modality"] = "image"
                            elif mime_type.startswith("video/"):
                                metadata["modality"] = "video"
                            elif mime_type.startswith("audio/"):
                                metadata["modality"] = "audio"
                            else:
                                metadata["modality"] = "text"
                        # Fall back to chunk_content_type (used by Ragie)
                        elif "chunk_content_type" in metadata:
                            content_type = metadata.get("chunk_content_type", "").lower()
                            if content_type == "image":
                                metadata["modality"] = "image"
                            elif content_type == "video":
                                metadata["modality"] = "video"
                            elif content_type == "audio":
                                metadata["modality"] = "audio"
                            else:
                                metadata["modality"] = "text"

                scored_chunks.append(
                    ScoredChunk(
                        text=chunk.text if hasattr(chunk, "text") else "",
                        score=chunk.score if hasattr(chunk, "score") else None,
                        chunk_id=chunk.chunk_id if hasattr(chunk, "chunk_id") else None,
                        document_id=chunk.document_id if hasattr(chunk, "document_id") else None,
                        metadata=metadata,
                    )
                )

        return SearchResponse(
            scored_chunks=scored_chunks,
            query=request.query,
            total_chunks=len(scored_chunks),
        )

    except Exception as e:
        logger.error(f"Error retrieving documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))
