import base64
from fastapi import APIRouter, Depends, HTTPException
from core.security import get_current_user, AuthUser
from core.config import get_settings
from core.deps import get_supabase
from schemas.ingest import QueryRequest, QueryResponse, QueryMatch
from embed.embeddings import embed_texts, embed_images, embed_clip_texts
from data_upload.pinecone_services import query_vectors

# 👇 imports
from scripts.highlighting import find_highlights
from scripts.bm25_reranker import rerank_with_bm25

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
        elif req.route not in ("text", "image"):
            raise HTTPException(
                422,
                detail="route must be 'text' or 'image' (or omitted)."
            )
        else:
            chosen_route = req.route

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
    else:
        raise HTTPException(500, detail="Internal routing error")

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

    # --- Build matches with highlighting ---
    matches = []
    for m in getattr(result, "matches", []) or []:
        md = m["metadata"] if isinstance(m, dict) else getattr(m, "metadata", {}) or {}
        bucket = md.get("bucket")
        storage_path = md.get("storage_path")

        signed_url = None
        if bucket and storage_path:
            try:
                res = supabase.storage.from_(bucket).create_signed_url(
                    storage_path, expires_in=3600
                )
                signed_url = res.get("signedURL")
            except Exception as e:
                print(f"Signed URL creation failed: {e}")

        # add signed_url to metadata
        md = md | {"signed_url": signed_url}

        # 🔑 Add highlighting for text-based metadata
        if "text" in md and req.query_text:
            md["highlight_spans"] = find_highlights(md["text"], req.query_text)

        matches.append(
            QueryMatch(
                id=m["id"] if isinstance(m, dict) else getattr(m, "id", ""),
                score=m["score"] if isinstance(m, dict) else getattr(m, "score", 0.0),
                metadata=md,
            )
        )

    # --- BM25 re-ranking (text only) ---
    if req.query_text:
        matches = rerank_with_bm25(req.query_text, matches, req.bm25_weight)

    return QueryResponse(
        matches=matches,
        top_k=req.top_k,
        route=chosen_route,
        namespace=user_id
    )
