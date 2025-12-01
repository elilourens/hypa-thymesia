"""
API endpoints for image auto-tagging functionality.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from core.deps import get_supabase
from core.security import get_current_user, AuthUser
from tagging import (
    tag_image,
    get_tags_for_chunk,
    search_chunks_by_tags,
    get_popular_tags,
)


router = APIRouter()


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
    from ..data_upload.pinecone_services import query_vectors

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
    user: AuthUser = Depends(get_current_user)
):
    """
    Search for images by detected object tags.

    Returns image chunks that contain the specified tags.
    """
    user_id = user.id

    results = await search_chunks_by_tags(
        user_id=user_id,
        tags=request.tags,
        min_confidence=request.min_confidence,
        limit=request.limit
    )

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
