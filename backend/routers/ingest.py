# app/routers/ingest.py
import os
import base64
from uuid import uuid4
from tempfile import NamedTemporaryFile
from typing import List, Any, Dict, Optional, Union
from datetime import datetime

from dotenv import load_dotenv
from fastapi import APIRouter, File, UploadFile, HTTPException, Query
from pydantic import BaseModel, Field

from data_upload.supabase_text_services import (
    upload_text_to_bucket,
    ingest_text_chunks,  # must support extra_vector_metadata (optional)
)
from data_upload.supabase_image_services import (
    upload_image_to_bucket,
    ingest_single_image,
)
from data_upload.pinecone_services import delete_vectors_by_ids, query_vectors
from supabase import create_client, Client

# LangChain-based metadata-extracting chunker
from ingestion.text.extract_text import extract_text_metadata

# embedding functions
from embed.embeddings import embed_texts, embed_images

router = APIRouter(prefix="/ingest", tags=["ingestion"])
load_dotenv()

# Supabase client (needed for deletion)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Shared model/dim for both text+image
EMBED_MODEL = os.getenv("EMBED_MODEL", "clip-ViT-B-32")
EMBED_DIM = int(os.getenv("EMBED_DIM", "512"))


@router.post("/upload-text-and-images")
async def ingest_text_and_image_files(file: UploadFile = File(...)):
    user_id = "dev_user"  # TODO: replace with real auth user id

    content = await file.read()
    ext = file.filename.rsplit(".", 1)[-1].lower()
    suffix = f".{ext}"

    supported_text = ("docx", "pdf", "txt", "md")  # keep in sync with extract_text.py
    supported_images = ("png", "jpeg", "jpg", "webp")

    if ext not in supported_text + supported_images:
        raise HTTPException(400, detail=f"Unsupported file type: {ext}")

    # IMAGE PATH
    if ext in supported_images:
        storage_path = upload_image_to_bucket(content, file.filename)
        if not storage_path:
            raise HTTPException(500, detail="Failed to upload image to storage")

        image_vectors = await embed_images([content])
        result = ingest_single_image(
            user_id=user_id,
            filename=file.filename,
            storage_path=storage_path,
            file_bytes=content,
            mime_type=file.content_type or "image/jpeg",
            embedding_model=EMBED_MODEL,
            embedding_dim=EMBED_DIM,
            embed_image_vectors=image_vectors,
            namespace=user_id,
            doc_id=str(uuid4()),
            embedding_version=1,
        )
        return {"doc_id": result["doc_id"], "chunks_ingested": result["vector_count"]}

    # TEXT PATH
    storage_path = upload_text_to_bucket(content, file.filename)
    if not storage_path:
        raise HTTPException(500, detail="Failed to upload text to storage")

    # Write temp file for the extractor
    with NamedTemporaryFile(prefix="upload_", suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if ext in supported_text:
            # Uses LangChain loaders + 20-char overlap + char offsets
            meta_out = extract_text_metadata(tmp_path, user_id=user_id, max_chunk_size=800)
        else:
            meta_out = {"text_chunks": []}
        chunks: List[Dict[str, Any]] = meta_out.get("text_chunks", [])
    finally:
        os.unlink(tmp_path)

    if not chunks:
        raise HTTPException(422, detail="No text chunks were extracted")

    texts = [c["chunk_text"] for c in chunks]
    text_vectors = await embed_texts(texts)

    # Build extra metadata to store alongside each vector for better UX/debugging
    extra_metas: List[Dict[str, Any]] = []
    for c in chunks:
        extra_metas.append(
            {
                "page_number": c.get("page_number"),
                "char_start": c.get("char_start"),
                "char_end": c.get("char_end"),
                # a small preview to display in UIs
                "preview": (c.get("chunk_text") or "")[:180].replace("\n", " "),
            }
        )

    # NOTE: ingest_text_chunks must be updated to accept and merge `extra_vector_metadata`
    result = ingest_text_chunks(
        user_id=user_id,
        filename=file.filename,
        storage_path=storage_path,
        text_chunks=texts,
        mime_type=file.content_type or "text/plain",
        embedding_model=EMBED_MODEL,
        embedding_dim=EMBED_DIM,
        embed_text_vectors=text_vectors,
        namespace=user_id,
        doc_id=str(uuid4()),
        embedding_version=1,
        extra_vector_metadata=extra_metas,  # <-- new optional param
    )

    return {"doc_id": result["doc_id"], "chunks_ingested": result["vector_count"]}


@router.delete("/delete-document")
async def delete_document(
    doc_id: str = Query(..., description="The UUID of the document to delete"),
    user_id: str = Query(..., description="User/namespace ID"),
):
    """
    Deletes all vectors from Pinecone and the related files/chunks in Supabase for a given doc_id.
    """
    # 1) Fetch all vector IDs + file info for the doc
    q = (
        supabase.table("app_vector_registry")
        .select("vector_id,app_chunks!inner(bucket,storage_path)")
        .eq("app_chunks.doc_id", doc_id)
    ).execute()

    rows = q.data or []
    if not rows:
        raise HTTPException(404, detail="No vectors found for this document")

    vector_ids = [r["vector_id"] for r in rows]
    files = {(r["app_chunks"]["bucket"], r["app_chunks"]["storage_path"]) for r in rows}

    # 2) Delete from Pinecone
    delete_vectors_by_ids(vector_ids, namespace=user_id)

    # 3) Delete files from Supabase storage
    for bucket, path in files:
        try:
            supabase.storage.from_(bucket).remove([path])
        except Exception as e:
            print(f"Storage delete failed for {bucket}/{path}: {e}")

    # 4) Delete chunks (FK cascade removes registry entries)
    supabase.table("app_chunks").delete().eq("doc_id", doc_id).execute()

    return {
        "deleted_vectors": len(vector_ids),
        "deleted_files": len(files),
        "doc_id": doc_id,
        "status": "deleted",
    }


# ----- QUERY API -----

ALLOWED_MODALITIES = {"text", "image"}

class QueryRequest(BaseModel):
    # Provide either query_text OR image_b64 (not both)
    query_text: str | None = Field(default=None, description="Natural-language query text.")
    image_b64: str | None = Field(default=None, description="Base64-encoded image to use as the query vector.")
    top_k: int = Field(default=10, ge=1, le=200)
    # Can be "text", "image", "any"/"both", or a list like ["text","image"]
    modality_filter: Union[str, List[str]] = Field(
        default="both",
        description="Accepts 'text', 'image', 'any'/'both', or a list like ['text','image']."
    )
    user_id: str = Field(default="dev_user", description="Namespace/user id for multi-tenant isolation.")


class QueryMatch(BaseModel):
    id: str
    score: float
    metadata: Dict[str, Any]


class QueryResponse(BaseModel):
    matches: List[QueryMatch]
    top_k: int
    modality_filter: str
    namespace: str


def _normalize_modality_filter(modality_filter: Union[str, List[str]]) -> Optional[Dict[str, Any]]:
    """
    Returns a Pinecone metadata filter dict or None (meaning both).
    - "text"  -> {"modality": {"$eq": "text"}}
    - "image" -> {"modality": {"$eq": "image"}}
    - "both"/"any" or ["text","image"] -> None (no filter)
    - ["text"] or ["image"] -> like $eq above
    - ["text","image","..."] -> 422 (invalid)
    """
    if isinstance(modality_filter, str):
        val = modality_filter.lower().strip()
        if val in ("any", "both"):
            return None  # no filter: return both
        if val in ALLOWED_MODALITIES:
            return {"modality": {"$eq": val}}
        raise HTTPException(422, detail="modality_filter must be 'text', 'image', 'any'/'both', or a list like ['text','image'].")

    # it's a list
    modes = {m.lower().strip() for m in modality_filter}
    if not modes or not modes.issubset(ALLOWED_MODALITIES):
        raise HTTPException(422, detail=f"modality_filter list must be subset of {sorted(ALLOWED_MODALITIES)}.")

    if len(modes) == 1:
        only = next(iter(modes))
        return {"modality": {"$eq": only}}
    # both — no filter needed; if you want an explicit $in, uncomment below
    # return {"modality": {"$in": sorted(list(modes))}}
    return None


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(req: QueryRequest):
    # Basic validation: exactly one of query_text or image_b64
    if bool(req.query_text) == bool(req.image_b64):
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one of 'query_text' or 'image_b64'."
        )

    pinecone_filter = _normalize_modality_filter(req.modality_filter)

    # Turn the query into an embedding
    if req.query_text:
        # Text query
        query_vecs = await embed_texts([req.query_text])
        query_vec = query_vecs[0]
    else:
        # Image query
        try:
            img_bytes = base64.b64decode(req.image_b64)
        except Exception:
            raise HTTPException(422, detail="image_b64 is not valid base64.")
        query_vecs = await embed_images([img_bytes])
        query_vec = query_vecs[0]

    # Pinecone similarity search
    try:
        result = query_vectors(
            vector=query_vec,
            top_k=req.top_k,
            namespace=req.user_id,           # match your ingestion namespace
            metadata_filter=pinecone_filter,
            include_metadata=True,
        )
    except Exception as e:
        raise HTTPException(500, detail=f"Pinecone query failed: {e}")

    # Normalize response
    matches = []
    for m in getattr(result, "matches", []) or []:
        matches.append(QueryMatch(
            id=m["id"] if isinstance(m, dict) else getattr(m, "id", ""),
            score=m["score"] if isinstance(m, dict) else getattr(m, "score", 0.0),
            metadata=m["metadata"] if isinstance(m, dict) else getattr(m, "metadata", {}) or {},
        ))

    # Echo a normalized, human-readable modality summary
    modality_echo = (
        "both" if pinecone_filter is None else
        ("text" if pinecone_filter.get("modality", {}).get("$eq") == "text" else "image")
    )

    return QueryResponse(
        matches=matches,
        top_k=req.top_k,
        modality_filter=modality_echo,
        namespace=req.user_id,
    )
