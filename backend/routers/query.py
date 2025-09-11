import base64
from fastapi import APIRouter, Depends, HTTPException
from core.security import get_current_user, AuthUser
from core.config import get_settings
from schemas.ingest import QueryRequest, QueryResponse, QueryMatch
from embed.embeddings import embed_texts, embed_images, embed_clip_texts
from data_upload.pinecone_services import query_vectors

router = APIRouter(prefix="/ingest", tags=["ingestion"])

@router.post("/query", response_model=QueryResponse)
async def query_endpoint(
    req: QueryRequest,  # NOTE: ensure QueryRequest has Optional[str] group_id
    auth: AuthUser = Depends(get_current_user),
    settings = Depends(get_settings),
):
    if bool(req.query_text) == bool(req.image_b64):
        raise HTTPException(422, detail="Provide exactly one of 'query_text' or 'image_b64'.")

    user_id = auth.id

    # Routing
    if req.image_b64 is not None:
        chosen_route = "image"
    else:
        if req.route is None:
            chosen_route = "text"
        elif req.route not in ("text", "image"):
            raise HTTPException(422, detail="route must be 'text' or 'image' (or omitted).")
        else:
            chosen_route = req.route

    # Embeddings
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

    # 🔑 Group filter logic
    meta_filter = None
    if req.group_id is not None:
        if req.group_id == "":
            # Special case: "ungrouped only"
            meta_filter = {
                "$or": [
                    {"group_id": {"$exists": False}},
                    {"group_id": {"$eq": None}},
                ]
            }
        else:
            meta_filter = {"group_id": {"$eq": req.group_id}}

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

    matches = [
        QueryMatch(
            id=(m["id"] if isinstance(m, dict) else getattr(m, "id", "")),
            score=(m["score"] if isinstance(m, dict) else getattr(m, "score", 0.0)),
            metadata=(m["metadata"] if isinstance(m, dict) else getattr(m, "metadata", {}) or {}),
        )
        for m in getattr(result, "matches", []) or []
    ]

    return QueryResponse(matches=matches, top_k=req.top_k, route=chosen_route, namespace=user_id)

