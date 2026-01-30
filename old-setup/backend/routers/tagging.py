"""
API endpoints for image and document auto-tagging functionality.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from core.deps import get_supabase
from core.security import get_current_user, AuthUser
from tagging import (
    tag_image,
    get_tags_for_chunk,
    get_popular_tags,
)
from tagging.document_tagger import get_document_tagger


router = APIRouter(prefix="/tagging", tags=["tagging"])


class TagImageRequest(BaseModel):
    """Request body for tagging a single image."""
    chunk_id: str = Field(..., description="Image chunk ID to tag")


class TagImageResponse(BaseModel):
    """Response for image tagging."""
    chunk_id: str
    verified_tags: List[Dict[str, Any]]
    candidate_tags: List[Dict[str, Any]]
    processing_time_ms: float


class GetTagsResponse(BaseModel):
    """Response for getting tags."""
    chunk_id: str
    tags: List[Dict[str, Any]]


class SearchByTagsRequest(BaseModel):
    """Request body for searching by tags."""
    tags: List[str] = Field(..., description="List of tag names to search for")
    min_confidence: float = Field(0.7, ge=0.0, le=1.0, description="Minimum confidence threshold")
    limit: int = Field(50, ge=1, le=200, description="Maximum number of results")


class SearchByTagsResponse(BaseModel):
    """Response for tag-based search."""
    results: List[Dict[str, Any]]
    count: int


class PopularTagsResponse(BaseModel):
    """Response for popular tags."""
    tags: List[Dict[str, Any]]


@router.post("/tag-upload", response_model=TagImageResponse)
async def tag_uploaded_image(
    request: TagImageRequest,
    user: AuthUser = Depends(get_current_user)
):
    """
    Trigger auto-tagging for a specific uploaded image chunk.

    This endpoint runs the two-stage CLIP + OWL-ViT pipeline:
    1. CLIP generates candidate labels
    2. OWL-ViT verifies and locates objects
    3. Results stored in database
    """
    user_id = user.id
    chunk_id = request.chunk_id

    # Fetch chunk metadata and embedding
    supabase = get_supabase()

    # Get chunk info
    chunk_result = (
        supabase.table("app_chunks")
        .select("doc_id, storage_path, bucket, modality")
        .eq("chunk_id", chunk_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not chunk_result.data:
        raise HTTPException(status_code=404, detail="Chunk not found")

    chunk = chunk_result.data[0]

    # Verify it's an image chunk
    if chunk["modality"] != "image":
        raise HTTPException(status_code=400, detail="Chunk is not an image")

    # Get image embedding from Pinecone
    from data_upload.pinecone_services import query_vectors

    vector_result = await query_vectors(
        query_embedding=None,  # Not used, we just need to fetch by ID
        namespace=user_id,
        top_k=1,
        filter={"chunk_id": chunk_id},
        index_type="image"
    )

    if not vector_result or "matches" not in vector_result or not vector_result["matches"]:
        raise HTTPException(status_code=404, detail="Image embedding not found")

    image_embedding = vector_result["matches"][0]["values"]

    # Download image from Supabase storage
    storage_path = chunk["storage_path"]
    bucket = chunk["bucket"]

    try:
        image_bytes = supabase.storage.from_(bucket).download(storage_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download image: {str(e)}")

    # Run tagging pipeline
    result = await tag_image(
        chunk_id=chunk_id,
        image_embedding=image_embedding,
        image_bytes=image_bytes,
        user_id=user_id,
        doc_id=chunk["doc_id"],
        store_candidates=True  # Store CLIP candidates for debugging
    )

    return TagImageResponse(**result)


@router.get("/images/{chunk_id}/tags", response_model=GetTagsResponse)
async def get_image_tags(
    chunk_id: str,
    verified_only: bool = True,
    user: AuthUser = Depends(get_current_user)
):
    """
    Retrieve tags for a specific image chunk.

    Query Parameters:
    - verified_only: Only return OWL-ViT verified tags (default: true)
    """
    user_id = user.id

    tags = await get_tags_for_chunk(
        chunk_id=chunk_id,
        user_id=user_id,
        verified_only=verified_only
    )

    return GetTagsResponse(chunk_id=chunk_id, tags=tags)


@router.post("/search/by-tags", response_model=SearchByTagsResponse)
async def search_images_by_tags(
    request: SearchByTagsRequest,
    group_id: Optional[str] = None,
    user: AuthUser = Depends(get_current_user)
):
    """
    Search for images by detected object tags.

    Returns image chunks that contain the specified tags.

    Query Parameters:
    - group_id: Optional group filter (null for ungrouped, omit for all)
    """
    user_id = user.id
    supabase = get_supabase()

    # Query image tags
    query = (
        supabase.table("app_image_tags")
        .select("chunk_id, tag_name, confidence, bbox")
        .eq("user_id", user_id)
        .eq("tag_type", "image")
        .in_("tag_name", request.tags)
        .gte("confidence", request.min_confidence)
        .not_.is_("chunk_id", "null")
    )

    tags_result = query.execute()

    # Group by chunk_id
    chunk_map: Dict[str, Dict[str, Any]] = {}
    for tag in tags_result.data or []:
        chunk_id = tag["chunk_id"]
        if chunk_id not in chunk_map:
            chunk_map[chunk_id] = {
                "chunk_id": chunk_id,
                "tags": []
            }
        chunk_map[chunk_id]["tags"].append({
            "tag_name": tag["tag_name"],
            "confidence": tag["confidence"],
            "bbox": tag.get("bbox")
        })

    # Get chunk metadata and filter by group
    results = []
    for chunk_id, tag_data in chunk_map.items():
        # Fetch chunk metadata including doc_id
        chunk_result = (
            supabase.table("app_chunks")
            .select("chunk_id, doc_id, storage_path, bucket, mime_type")
            .eq("chunk_id", chunk_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not chunk_result.data:
            continue

        chunk = chunk_result.data[0]
        doc_id = chunk["doc_id"]

        # Get document metadata to check group
        doc_result = (
            supabase.table("app_doc_meta")
            .select("group_id")
            .eq("doc_id", doc_id)
            .execute()
        )

        if not doc_result.data:
            continue

        doc = doc_result.data[0]

        # Apply group filter
        if group_id is not None:
            if group_id == "":
                # Filter for ungrouped
                if doc.get("group_id") is not None:
                    continue
            else:
                # Filter for specific group
                if doc.get("group_id") != group_id:
                    continue

        results.append({
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "group_id": doc.get("group_id"),
            "tags": tag_data["tags"],
            "storage_path": chunk["storage_path"],
            "bucket": chunk["bucket"],
            "mime_type": chunk.get("mime_type"),
            "avg_confidence": sum(t["confidence"] for t in tag_data["tags"]) / len(tag_data["tags"])
        })

    # Sort by confidence and limit
    results.sort(key=lambda x: x["avg_confidence"], reverse=True)
    results = results[:request.limit]

    return SearchByTagsResponse(results=results, count=len(results))


@router.get("/tags/popular", response_model=PopularTagsResponse)
async def get_popular_tags_endpoint(
    limit: int = 20,
    verified_only: bool = True,
    user: AuthUser = Depends(get_current_user)
):
    """
    Get most frequently occurring tags for the current user.

    Useful for autocomplete and tag suggestions.

    Query Parameters:
    - limit: Number of top tags to return (default: 20)
    - verified_only: Only count verified tags (default: true)
    """
    user_id = user.id

    tags = await get_popular_tags(
        user_id=user_id,
        limit=limit,
        verified_only=verified_only
    )

    return PopularTagsResponse(tags=tags)


# ========== Document Tagging Endpoints ==========


class TagDocumentRequest(BaseModel):
    """Request body for tagging a document chunk."""
    chunk_id: str = Field(..., description="Text chunk ID to tag")


class TagDocumentResponse(BaseModel):
    """Response for document tagging."""
    chunk_id: str
    tags: List[Dict[str, Any]]
    processing_time_ms: float
    preview_chars: int


class GetDocumentTagsResponse(BaseModel):
    """Response for getting document tags."""
    chunk_id: str
    tags: List[Dict[str, Any]]
    tag_categories: Optional[Dict[str, List[str]]] = None


@router.post("/tag-document", response_model=TagDocumentResponse)
async def tag_document_chunk(
    request: TagDocumentRequest,
    user: AuthUser = Depends(get_current_user)
):
    """
    Trigger LLM-based tagging for a specific text document chunk.

    This endpoint uses Ollama/Mistral to analyze the document and assign
    relevant tags across multiple categories (document type, domain, topic, etc.).
    """
    user_id = user.id
    chunk_id = request.chunk_id

    # Fetch chunk metadata
    supabase = get_supabase()

    chunk_result = (
        supabase.table("app_chunks")
        .select("doc_id, storage_path, bucket, modality")
        .eq("chunk_id", chunk_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not chunk_result.data:
        raise HTTPException(status_code=404, detail="Chunk not found")

    chunk = chunk_result.data[0]

    # Verify it's a text chunk
    if chunk["modality"] != "text":
        raise HTTPException(status_code=400, detail="Chunk is not a text document")

    # Download text content from Supabase storage
    storage_path = chunk["storage_path"]
    bucket = chunk["bucket"]

    try:
        text_bytes = supabase.storage.from_(bucket).download(storage_path)
        text_content = text_bytes.decode("utf-8") if isinstance(text_bytes, bytes) else str(text_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download text: {str(e)}")

    # Get document tagger and run tagging
    tagger = get_document_tagger()

    result = await tagger.tag_document(
        text_content=text_content,
        filename="",  # Could fetch from parent doc if needed
        min_confidence=0.5
    )

    if "error" in result:
        raise HTTPException(status_code=500, detail=f"Tagging failed: {result['error']}")

    # Store tags in database (document-level, not chunk-level)
    stored_count = await tagger.store_document_tags(
        doc_id=chunk["doc_id"],
        user_id=user_id,
        tags=result["tags"]
    )

    # Convert DocumentTag objects to dicts for response
    tag_dicts = [
        {
            "tag_name": tag.tag_name,
            "category": tag.category,
            "confidence": tag.confidence,
            "reasoning": tag.reasoning
        }
        for tag in result["tags"]
    ]

    return TagDocumentResponse(
        chunk_id=chunk_id,
        tags=tag_dicts,
        processing_time_ms=result["processing_time_ms"],
        preview_chars=result["preview_chars"]
    )


@router.get("/documents/{doc_id}/tags", response_model=GetDocumentTagsResponse)
async def get_document_tags(
    doc_id: str,
    group_by_category: bool = False,
    user: AuthUser = Depends(get_current_user)
):
    """
    Retrieve tags for a specific document (document-level tags).

    Query Parameters:
    - group_by_category: Group tags by category (default: false)
    """
    user_id = user.id
    supabase = get_supabase()

    # Fetch document-level tags from database (chunk_id IS NULL)
    # Limit to top 3 most confident tags
    tags_result = (
        supabase.table("app_image_tags")
        .select("tag_name, category, confidence, reasoning, verified")
        .eq("doc_id", doc_id)
        .eq("user_id", user_id)
        .eq("tag_type", "document")
        .is_("chunk_id", "null")
        .order("confidence", desc=True)
        .limit(3)
        .execute()
    )

    tags = tags_result.data or []

    # Optionally group by category
    tag_categories = None
    if group_by_category:
        tag_categories = {}
        for tag in tags:
            category = tag.get("category", "unknown")
            if category not in tag_categories:
                tag_categories[category] = []
            tag_categories[category].append(tag["tag_name"])

    return GetDocumentTagsResponse(
        chunk_id=doc_id,  # Return doc_id in response for consistency
        tags=tags,
        tag_categories=tag_categories
    )


@router.post("/search/by-document-tags", response_model=SearchByTagsResponse)
async def search_documents_by_tags(
    request: SearchByTagsRequest,
    category: Optional[str] = None,
    group_id: Optional[str] = None,
    user: AuthUser = Depends(get_current_user)
):
    """
    Search for documents by LLM-assigned tags.

    Returns full document metadata including all chunks.

    Query Parameters:
    - category: Optional category filter (e.g., "document_type", "subject_domain")
    - group_id: Optional group filter (null for ungrouped, omit for all)
    """
    user_id = user.id
    supabase = get_supabase()

    # Build query for document-level tags (chunk_id IS NULL)
    query = (
        supabase.table("app_image_tags")
        .select("doc_id, tag_name, confidence, category")
        .eq("user_id", user_id)
        .eq("tag_type", "document")
        .is_("chunk_id", "null")
        .in_("tag_name", request.tags)
        .gte("confidence", request.min_confidence)
    )

    # Add category filter if specified
    if category:
        query = query.eq("category", category)

    tags_result = query.execute()

    # Group results by doc_id
    doc_map: Dict[str, Dict[str, Any]] = {}
    for tag in tags_result.data or []:
        doc_id = tag["doc_id"]
        if doc_id not in doc_map:
            doc_map[doc_id] = {
                "doc_id": doc_id,
                "tags": [],
                "avg_confidence": 0.0
            }
        doc_map[doc_id]["tags"].append({
            "tag_name": tag["tag_name"],
            "confidence": tag["confidence"],
            "category": tag.get("category")
        })

    # Get document metadata and chunks for matching docs
    results = []
    for doc_id, tag_data in doc_map.items():
        # Calculate average confidence
        avg_conf = sum(t["confidence"] for t in tag_data["tags"]) / len(tag_data["tags"])

        # Fetch document metadata
        doc_query = (
            supabase.table("app_doc_meta")
            .select("doc_id, user_id, group_id")
            .eq("doc_id", doc_id)
            .eq("user_id", user_id)
        )

        doc_result = doc_query.execute()

        if not doc_result.data:
            continue

        doc = doc_result.data[0]

        # Apply group filter if specified
        if group_id is not None:
            if group_id == "":
                # Filter for ungrouped documents
                if doc.get("group_id") is not None:
                    continue
            else:
                # Filter for specific group
                if doc.get("group_id") != group_id:
                    continue

        # Fetch chunks for this document
        chunks_result = (
            supabase.table("app_chunks")
            .select("chunk_id, chunk_index, modality, storage_path, bucket, mime_type, size_bytes")
            .eq("doc_id", doc_id)
            .eq("user_id", user_id)
            .order("chunk_index")
            .execute()
        )

        chunks = chunks_result.data or []

        # Get filename and mime_type from first chunk's storage_path
        filename = None
        mime_type = None
        if chunks:
            first_chunk = chunks[0]
            mime_type = first_chunk.get("mime_type")

            # Extract filename from storage_path (format: uploads/uuid_filename.ext)
            storage_path = first_chunk.get("storage_path", "")
            if storage_path:
                # Get the last part after the last slash
                path_parts = storage_path.split("/")
                if path_parts:
                    # Remove UUID prefix (format: uuid_filename.ext)
                    filename_with_uuid = path_parts[-1]
                    # Split on first underscore to remove UUID
                    if "_" in filename_with_uuid:
                        filename = filename_with_uuid.split("_", 1)[1]
                    else:
                        filename = filename_with_uuid

        results.append({
            "doc_id": doc_id,
            "filename": filename,
            "group_id": doc.get("group_id"),
            "tags": tag_data["tags"],
            "avg_confidence": avg_conf,
            "chunks": chunks,
            "text_chunks": len([c for c in chunks if c["modality"] == "text"]),
            "image_chunks": len([c for c in chunks if c["modality"] == "image"])
        })

    # Sort by average confidence
    results.sort(key=lambda x: x["avg_confidence"], reverse=True)

    # Limit results
    results = results[:request.limit]

    return SearchByTagsResponse(results=results, count=len(results))


@router.get("/tags/available")
async def get_available_document_tags(
    user: AuthUser = Depends(get_current_user)
):
    """
    Get all available document tags organized by category.

    Returns the complete tag taxonomy from document_labels.json.
    """
    import json
    import os
    from pathlib import Path

    # Load document_labels.json
    config_path = Path(__file__).parent.parent / "config" / "document_labels.json"

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            labels_data = json.load(f)

        return {
            "categories": labels_data.get("categories", {})
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load tag taxonomy: {str(e)}")


@router.get("/tags/user-tags")
async def get_user_document_tags(
    group_by_category: bool = True,
    tag_type: str = "document",
    user: AuthUser = Depends(get_current_user)
):
    """
    Get all tags that exist in the user's documents or images.

    Returns only tags that have been assigned to at least one document/image.

    Query Parameters:
    - group_by_category: Group tags by category (default: true)
    - tag_type: Type of tags to fetch - "document" or "image" (default: "document")
    """
    user_id = user.id
    supabase = get_supabase()

    # Build query based on tag type
    query = (
        supabase.table("app_image_tags")
        .select("tag_name, category, confidence")
        .eq("user_id", user_id)
        .eq("tag_type", tag_type)
    )

    # For document tags, only get document-level tags (chunk_id IS NULL)
    # For image tags, get chunk-level tags (chunk_id IS NOT NULL)
    if tag_type == "document":
        query = query.is_("chunk_id", "null")
    else:
        query = query.not_.is_("chunk_id", "null")

    tags_result = query.execute()
    tags_data = tags_result.data or []

    if not group_by_category:
        # Return flat list of unique tags
        unique_tags = list(set(tag["tag_name"] for tag in tags_data))
        return {
            "tags": sorted(unique_tags),
            "count": len(unique_tags)
        }

    # Group by category
    categories: Dict[str, List[str]] = {}
    for tag in tags_data:
        category = tag.get("category") or "uncategorized"
        tag_name = tag["tag_name"]

        if category not in categories:
            categories[category] = []

        if tag_name not in categories[category]:
            categories[category].append(tag_name)

    # Sort tags within each category
    for category in categories:
        categories[category].sort()

    return {
        "categories": categories,
        "total_unique_tags": sum(len(tags) for tags in categories.values())
    }
