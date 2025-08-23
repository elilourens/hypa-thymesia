# app/routers/ingest.py
import os
import base64
from uuid import uuid4
from tempfile import NamedTemporaryFile
from typing import List, Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import (
    APIRouter,
    File,
    UploadFile,
    HTTPException,
    Query,
    Depends,
)
from pydantic import BaseModel, Field

from data_upload.supabase_text_services import (
    upload_text_to_bucket,
    ingest_text_chunks,
)
from data_upload.supabase_image_services import (
    upload_image_to_bucket,
    ingest_single_image,
)
from data_upload.pinecone_services import delete_vectors_by_ids, query_vectors
from supabase import create_client, Client

from ingestion.text.extract_text import extract_text_metadata
from embed.embeddings import embed_texts, embed_images, embed_clip_texts  # <-- add CLIP text

# --- Auth (JWKS) ---
import jwt
from jwt import PyJWKClient
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# --------------------------------------------------------------------
# Router & env
# --------------------------------------------------------------------
router = APIRouter(prefix="/ingest", tags=["ingestion"])
load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_KEY (service role) must be set in backend env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# These are defaults; routing logic below decides which encoder/index is used.
EMBED_MODEL = os.getenv("EMBED_MODEL", "clip-ViT-B-32")
EMBED_DIM = int(os.getenv("EMBED_DIM", "512"))

# --------------------------------------------------------------------
# JWT verification (ES256/RS256 via JWKS)
# --------------------------------------------------------------------
security = HTTPBearer()
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
_jwks = PyJWKClient(JWKS_URL)

class AuthUser:
    def __init__(self, sub: str, email: Optional[str] = None):
        self.id = sub
        self.email = email

def get_current_user(auth: HTTPAuthorizationCredentials = Depends(security)) -> AuthUser:
    token = auth.credentials
    try:
        key = _jwks.get_signing_key_from_jwt(token).key
        payload = jwt.decode(
            token,
            key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            options={"require": ["sub", "exp", "iat"]},
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {e}")
    return AuthUser(sub=payload["sub"], email=payload.get("email"))

# --------------------------------------------------------------------
# Models
# --------------------------------------------------------------------
# Stored chunk modalities (what’s actually in app_chunks)
ALLOWED_MODALITIES = {"text", "image"}

class QueryRequest(BaseModel):
    # Provide exactly one:
    query_text: Optional[str] = None
    image_b64: Optional[str] = None
    top_k: int = Field(default=10, ge=1, le=200)
    # No normalization. You either omit it (we infer), or set it explicitly to "text" or "image".
    # - For text queries:
    #     route="text"  -> search text index (MiniLM)
    #     route="image" -> search image index using CLIP **text** encoder
    # - For image queries:
    #     route is ignored; we always search the image index (CLIP image encoder)
    route: Optional[str] = None  # "text" | "image" | None

class QueryMatch(BaseModel):
    id: str
    score: float
    metadata: Dict[str, Any]

class QueryResponse(BaseModel):
    matches: List[QueryMatch]
    top_k: int
    route: str
    namespace: str

# --------------------------------------------------------------------
# Debug / health endpoint
# --------------------------------------------------------------------
@router.get("/whoami")
def whoami(auth: AuthUser = Depends(get_current_user)):
    return {"id": auth.id, "email": auth.email}

# --------------------------------------------------------------------
# Upload route (unchanged behavior, now routes to separate indexes under the hood)
# --------------------------------------------------------------------
@router.post("/upload-text-and-images")
async def ingest_text_and_image_files(
    file: UploadFile = File(...),
    auth: AuthUser = Depends(get_current_user),
):
    user_id = auth.id

    content = await file.read()
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    suffix = f".{ext}" if ext else ""

    supported_text = ("docx", "pdf", "txt", "md")
    supported_images = ("png", "jpeg", "jpg", "webp")

    if ext not in supported_text + supported_images:
        raise HTTPException(400, detail=f"Unsupported file type: {ext or 'unknown'}")

    # ---------------- IMAGE PATH ----------------
    if ext in supported_images:
        storage_path = upload_image_to_bucket(content, file.filename)
        if not storage_path:
            raise HTTPException(500, detail="Failed to upload image to storage")

        image_vectors = await embed_images([content])  # CLIP image embeddings (512-D)

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

    # ---------------- TEXT PATH ----------------
    storage_path = upload_text_to_bucket(content, file.filename)
    if not storage_path:
        raise HTTPException(500, detail="Failed to upload text to storage")

    # Write temp file for the extractor
    with NamedTemporaryFile(prefix="upload_", suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        meta_out = extract_text_metadata(tmp_path, user_id=user_id, max_chunk_size=800)
        chunks: List[Dict[str, Any]] = meta_out.get("text_chunks", [])
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    if not chunks:
        raise HTTPException(422, detail="No text chunks were extracted")

    texts = [c["chunk_text"] for c in chunks]
    text_vectors = await embed_texts(texts)  # MiniLM embeddings (384-D)

    # Optional UX metadata for each chunk
    extra_metas: List[Dict[str, Any]] = []
    for c in chunks:
        extra_metas.append(
            {
                "page_number": c.get("page_number"),
                "char_start": c.get("char_start"),
                "char_end": c.get("char_end"),
                "preview": (c.get("chunk_text") or "")[:180].replace("\n", " "),
            }
        )

    result = ingest_text_chunks(
        user_id=user_id,
        filename=file.filename,
        storage_path=storage_path,
        text_chunks=texts,
        mime_type=file.content_type or "text/plain",
        embedding_model="all-MiniLM-L12-v2",
        embedding_dim=384,
        embed_text_vectors=text_vectors,
        namespace=user_id,
        doc_id=str(uuid4()),
        embedding_version=1,
        extra_vector_metadata=extra_metas,
    )

    return {"doc_id": result["doc_id"], "chunks_ingested": result["vector_count"]}

# --------------------------------------------------------------------
# Delete document (now modality-aware)
# --------------------------------------------------------------------
@router.delete("/delete-document")
async def delete_document(
    doc_id: str = Query(..., description="The UUID of the document to delete"),
    auth: AuthUser = Depends(get_current_user),
):
    """
    Deletes vectors from Pinecone and related files/chunks in Supabase for a given doc_id.
    Enforces ownership via app_chunks.user_id. Routes deletions to the correct index
    based on app_chunks.modality.
    """
    user_id = auth.id

    # Pull vector ids + file locations + modality (owner-scoped)
    q = (
        supabase
        .table("app_vector_registry")
        .select("vector_id,app_chunks!inner(bucket,storage_path,modality)")
        .eq("app_chunks.doc_id", doc_id)
        .eq("app_chunks.user_id", user_id)
    ).execute()

    rows = q.data or []
    if not rows:
        raise HTTPException(404, detail="No vectors found for this document")

    text_ids: List[str] = []
    image_ids: List[str] = []
    files = set()

    for r in rows:
        ch = r["app_chunks"]
        files.add((ch["bucket"], ch["storage_path"]))
        if ch.get("modality") == "text":
            text_ids.append(r["vector_id"])
        elif ch.get("modality") == "image":
            image_ids.append(r["vector_id"])

    # Delete from Pinecone (scoped to tenant namespace)
    if text_ids:
        delete_vectors_by_ids(ids=text_ids, modality="text", namespace=user_id)
    if image_ids:
        delete_vectors_by_ids(ids=image_ids, modality="image", namespace=user_id)

    # Delete files from Supabase storage (best-effort)
    for bucket, path in files:
        try:
            supabase.storage.from_(bucket).remove([path])
        except Exception as e:
            print(f"Storage delete failed for {bucket}/{path}: {e}")

    # Delete chunk rows (owner-scoped)
    supabase.table("app_chunks").delete().eq("doc_id", doc_id).eq("user_id", user_id).execute()

    return {
        "deleted_vectors": len(text_ids) + len(image_ids),
        "deleted_files": len(files),
        "doc_id": doc_id,
        "status": "deleted",
    }

# --------------------------------------------------------------------
# Query (no normalization; explicit routing)
# --------------------------------------------------------------------
@router.post("/query", response_model=QueryResponse)
async def query_endpoint(
    req: QueryRequest,
    auth: AuthUser = Depends(get_current_user),
):
    # Exactly one of query_text or image_b64
    if bool(req.query_text) == bool(req.image_b64):
        raise HTTPException(422, detail="Provide exactly one of 'query_text' or 'image_b64'.")

    user_id = auth.id

    # Decide route explicitly (no normalization)
    if req.image_b64 is not None:
        chosen_route = "image"  # image->image (CLIP image encoder)
    else:
        # text query; default to text->text unless caller explicitly says image (text->image)
        if req.route is None:
            chosen_route = "text"
        elif req.route not in ("text", "image"):
            raise HTTPException(422, detail="route must be 'text' or 'image' (or omitted).")
        else:
            chosen_route = req.route

    # Build query vector according to chosen route
    if chosen_route == "text":
        # MiniLM text embeddings, search TEXT index
        vec = (await embed_texts([req.query_text]))[0]
        modality_arg = "text"
    elif chosen_route == "image":
        if req.image_b64 is not None:
            # CLIP image embeddings, search IMAGE index
            try:
                img_bytes = base64.b64decode(req.image_b64)
            except Exception:
                raise HTTPException(422, detail="image_b64 is not valid base64.")
            vec = (await embed_images([img_bytes]))[0]
            modality_arg = "image"
        else:
            # text->image with CLIP **text** encoder
            vec = (await embed_clip_texts([req.query_text]))[0]
            modality_arg = "clip_text"
    else:
        raise HTTPException(500, detail="Internal routing error")

    # Single-index similarity search in user's namespace (no metadata filter needed)
    try:
        result = query_vectors(
            vector=vec,
            modality=modality_arg,  # routes to the correct index and enforces dim
            top_k=req.top_k,
            namespace=user_id,
            metadata_filter=None,
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

    return QueryResponse(
        matches=matches,
        top_k=req.top_k,
        route=chosen_route,
        namespace=user_id,
    )
