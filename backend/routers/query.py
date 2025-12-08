import base64
from fastapi import APIRouter, Depends, HTTPException
from core.security import get_current_user, AuthUser
from core.config import get_settings
from core.deps import get_supabase
from schemas.ingest import QueryRequest, QueryResponse, QueryMatch
from embed.embeddings import embed_texts, embed_images, embed_clip_texts
from data_upload.pinecone_services import query_vectors, keyword_search_text

router = APIRouter(prefix="/ingest", tags=["ingestion"])


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(
    req: QueryRequest,
    auth: AuthUser = Depends(get_current_user),
    settings=Depends(get_settings),
    supabase=Depends(get_supabase),
):
    if bool(req.query_text) == bool(req.image_b64):
        raise HTTPException(
            422,
            detail="Provide exactly one of 'query_text' or 'image_b64'."
        )

    user_id = auth.id

    # --- Routing ---
    if req.image_b64 is not None:
        chosen_route = "image"
    else:
        if req.route is None:
            chosen_route = "text"
        elif req.route not in ("text", "image", "extracted_image"):  # UPDATED
            raise HTTPException(
                422,
                detail="route must be 'text', 'image', or 'extracted_image' (or omitted)."
            )
        else:
            chosen_route = req.route

    # --- Group filter ---
    meta_filter = None
    if req.group_id is not None:
        if req.group_id == "":
            meta_filter = {
                "$or": [
                    {"group_id": {"$exists": False}},
                    {"group_id": {"$eq": None}},
                ]
            }
        else:
            meta_filter = {"group_id": {"$eq": req.group_id}}

    # --- Keyword search mode (text only) ---
    if req.search_mode == "keyword" and chosen_route == "text":
        if not req.query_text:
            raise HTTPException(422, detail="Keyword search requires query_text")

        try:
            result = keyword_search_text(
                keywords=req.query_text,
                top_k=req.top_k,
                namespace=user_id,
                metadata_filter=meta_filter,
            )
        except Exception as e:
            raise HTTPException(500, detail=f"Keyword search failed: {e}")
    # --- Smart search mode (embedding-based) ---
    else:
        # --- Embeddings ---
        if chosen_route == "text":
            vec = (await embed_texts([req.query_text]))[0]
            modality_arg = "text"
        elif chosen_route == "image":
            if req.image_b64 is not None:
                try:
                    img_bytes = base64.b64decode(req.image_b64)
                except Exception:
                    raise HTTPException(422, detail="image_b64 is not valid base64.")
                vec = (await embed_images([img_bytes]))[0]
                modality_arg = "image"
            else:
                vec = (await embed_clip_texts([req.query_text]))[0]
                modality_arg = "clip_text"
        elif chosen_route == "extracted_image":  # NEW
            # Search extracted images using text query
            if req.query_text:
                vec = (await embed_clip_texts([req.query_text]))[0]
                modality_arg = "extracted_image"
            else:
                raise HTTPException(422, detail="extracted_image route requires query_text")
        else:
            raise HTTPException(500, detail="Internal routing error")

        # --- Pinecone query ---
        try:
            result = query_vectors(
                vector=vec,
                modality=modality_arg,
                top_k=req.top_k,
                namespace=user_id,
                metadata_filter=meta_filter,
                include_metadata=True,
            )
        except Exception as e:
            raise HTTPException(500, detail=f"Pinecone query failed: {e}")

    # --- Build matches ---
    matches = []

    # Handle both dict from keyword_search_text and object from query_vectors
    result_matches = result.get("matches") if isinstance(result, dict) else getattr(result, "matches", [])

    for m in result_matches or []:
        md = m.get("metadata") if isinstance(m, dict) else getattr(m, "metadata", {}) or {}

        # keep only bucket & path for later use by /storage/signed-url
        bucket = md.get("bucket")
        storage_path = md.get("storage_path")
        chunk_id = md.get("chunk_id")

        # For extracted images, also include parent doc info
        if md.get("source") == "extracted":
            md = md | {
                "bucket": bucket,
                "storage_path": storage_path,
                "parent_filename": md.get("parent_filename"),
                "parent_storage_path": md.get("parent_storage_path"),
                "parent_bucket": md.get("parent_bucket"),
                "page_number": md.get("page_number"),
                "public_url": md.get("public_url"),  # Direct image URL
            }
        else:
            md = md | {"bucket": bucket, "storage_path": storage_path}

        # Add tags for image results
        if md.get("modality") == "image" and chunk_id:
            try:
                # Query tags from database
                # Limit to top 3 most confident tags
                tags_result = supabase.table("app_image_tags").select("tag_name, confidence, bbox").eq(
                    "chunk_id", chunk_id
                ).eq("user_id", user_id).eq("tag_type", "image").eq("verified", True).order("confidence", desc=True).limit(3).execute()

                if tags_result.data:
                    md["tags"] = tags_result.data
            except Exception as e:
                import logging
                logging.warning(f"Failed to fetch tags for chunk {chunk_id}: {e}")

        # Add tags for text/document results (document-level tags, not chunk-level)
        if md.get("modality") == "text":
            # Get doc_id from metadata
            doc_id = md.get("doc_id")
            if doc_id:
                try:
                    # Query document-level tags from database (chunk_id IS NULL)
                    # Limit to top 3 most confident tags
                    tags_result = supabase.table("app_image_tags").select("tag_name, confidence, category, reasoning").eq(
                        "doc_id", doc_id
                    ).eq("user_id", user_id).eq("tag_type", "document").is_("chunk_id", "null").order("confidence", desc=True).limit(3).execute()

                    if tags_result.data:
                        md["tags"] = tags_result.data
                except Exception as e:
                    import logging
                    logging.warning(f"Failed to fetch document tags for doc {doc_id}: {e}")

        matches.append(
            QueryMatch(
                id=m["id"] if isinstance(m, dict) else getattr(m, "id", ""),
                score=m["score"] if isinstance(m, dict) else getattr(m, "score", 0.0),
                metadata=md,
            )
        )

    return QueryResponse(
        matches=matches,
        top_k=req.top_k,
        route=chosen_route,
        namespace=user_id,
    )