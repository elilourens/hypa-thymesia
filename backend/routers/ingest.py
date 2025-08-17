# app/routers/ingest.py
import os
import base64
from uuid import uuid4
from tempfile import NamedTemporaryFile
from typing import List, Any, Dict, Optional, Union

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
from embed.embeddings import embed_texts, embed_images

# --- Auth (JWKS) ---
import jwt
from jwt import PyJWKClient
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# --------------------------------------------------------------------
# Router & env
# --------------------------------------------------------------------
router = APIRouter(prefix="/ingest", tags=["ingestion"])
load_dotenv()

# Supabase URL/keys (server-side; KEY should be service_role or a server key)
SUPABASE_URL = os.environ["SUPABASE_URL"]  # crash early if missing
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_KEY (service role) must be set in backend env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Embedding defaults
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
    token = auth.credentials  # Swagger adds 'Bearer' automatically; this is raw JWT
    try:
        key = _jwks.get_signing_key_from_jwt(token).key
        payload = jwt.decode(
            token,
            key,
            algorithms=["ES256", "RS256"],   # Supabase new tokens are ES256; allow RS256 too
            audience="authenticated",
            options={"require": ["sub", "exp", "iat"]},
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {e}")
    return AuthUser(sub=payload["sub"], email=payload.get("email"))

# --------------------------------------------------------------------
# Models
# --------------------------------------------------------------------
ALLOWED_MODALITIES = {"text", "image"}

class QueryRequest(BaseModel):
    # Provide exactly one of these:
    query_text: Optional[str] = None
    image_b64: Optional[str] = None
    top_k: int = Field(default=10, ge=1, le=200)
    # "text", "image", "any"/"both", or a list like ["text","image"]
    modality_filter: Union[str, List[str]] = "both"

class QueryMatch(BaseModel):
    id: str
    score: float
    metadata: Dict[str, Any]

class QueryResponse(BaseModel):
    matches: List[QueryMatch]
    top_k: int
    modality_filter: str
    namespace: str

# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------
def _normalize_modality_filter(modality_filter: Union[str, List[str]]) -> Optional[Dict[str, Any]]:
    if isinstance(modality_filter, str):
        val = modality_filter.lower().strip()
        if val in ("any", "both"):
            return None
        if val in ALLOWED_MODALITIES:
            return {"modality": {"$eq": val}}
        raise HTTPException(422, detail="Invalid modality_filter")
    modes = {m.lower().strip() for m in modality_filter}
    if not modes or not modes.issubset(ALLOWED_MODALITIES):
        raise HTTPException(422, detail=f"modality_filter list must be subset of {sorted(ALLOWED_MODALITIES)}.")
    if len(modes) == 1:
        return {"modality": {"$eq": next(iter(modes))}}
    return None  # both

# --------------------------------------------------------------------
# Debug / health endpoint
# --------------------------------------------------------------------
@router.get("/whoami")
def whoami(auth: AuthUser = Depends(get_current_user)):
    return {"id": auth.id, "email": auth.email}

# --------------------------------------------------------------------
# Routes
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

        image_vectors = await embed_images([content])

        # NOTE: ensure your ingest_single_image writes user_id into app_chunks!
        result = ingest_single_image(
            user_id=user_id,
            filename=file.filename,
            storage_path=storage_path,
            file_bytes=content,
            mime_type=file.content_type or "image/jpeg",
            embedding_model=EMBED_MODEL,
            embedding_dim=EMBED_DIM,
            embed_image_vectors=image_vectors,
            namespace=user_id,     # tenant namespace in Pinecone
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
    text_vectors = await embed_texts(texts)

    # Build extra metadata for each vector (optional UX fields)
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

    # IMPORTANT: ingest_text_chunks() must insert app_chunks with user_id=user_id
    result = ingest_text_chunks(
        user_id=user_id,
        filename=file.filename,
        storage_path=storage_path,
        text_chunks=texts,
        mime_type=file.content_type or "text/plain",
        embedding_model=EMBED_MODEL,
        embedding_dim=EMBED_DIM,
        embed_text_vectors=text_vectors,
        namespace=user_id,               # tenant namespace in Pinecone
        doc_id=str(uuid4()),
        embedding_version=1,
        extra_vector_metadata=extra_metas,
    )

    return {"doc_id": result["doc_id"], "chunks_ingested": result["vector_count"]}


@router.delete("/delete-document")
async def delete_document(
    doc_id: str = Query(..., description="The UUID of the document to delete"),
    auth: AuthUser = Depends(get_current_user),
):
    """
    Deletes vectors from Pinecone and related files/chunks in Supabase for a given doc_id.
    Enforces ownership via app_chunks.user_id.
    """
    user_id = auth.id

    # Join through app_chunks and scope to the owner
    q = (
        supabase.table("app_vector_registry")
        .select("vector_id,app_chunks!inner(bucket,storage_path)")
        .eq("app_chunks.doc_id", doc_id)
        .eq("app_chunks.user_id", user_id)   # <-- qualify the joined table
    ).execute()

    rows = q.data or []
    if not rows:
        raise HTTPException(404, detail="No vectors found for this document")

    vector_ids = [r["vector_id"] for r in rows]
    files = {(r["app_chunks"]["bucket"], r["app_chunks"]["storage_path"]) for r in rows}

    # 2) Delete from Pinecone (scoped to tenant namespace)
    delete_vectors_by_ids(vector_ids, namespace=user_id)

    # 3) Delete files from Supabase storage
    for bucket, path in files:
        try:
            supabase.storage.from_(bucket).remove([path])
        except Exception as e:
            # non-fatal
            print(f"Storage delete failed for {bucket}/{path}: {e}")

    # 4) Delete chunks (owner-scoped)
    supabase.table("app_chunks").delete().eq("doc_id", doc_id).eq("user_id", user_id).execute()

    return {
        "deleted_vectors": len(vector_ids),
        "deleted_files": len(files),
        "doc_id": doc_id,
        "status": "deleted",
    }


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(
    req: QueryRequest,
    auth: AuthUser = Depends(get_current_user),
):
    # Exactly one of query_text or image_b64
    if bool(req.query_text) == bool(req.image_b64):
        raise HTTPException(422, detail="Provide exactly one of 'query_text' or 'image_b64'.")

    user_id = auth.id
    pinecone_filter = _normalize_modality_filter(req.modality_filter)

    # Build query vector
    if req.query_text:
        query_vecs = await embed_texts([req.query_text])
        query_vec = query_vecs[0]
    else:
        try:
            img_bytes = base64.b64decode(req.image_b64 or "")
        except Exception:
            raise HTTPException(422, detail="image_b64 is not valid base64.")
        query_vecs = await embed_images([img_bytes])
        query_vec = query_vecs[0]

    # Pinecone similarity search in user's namespace
    try:
        result = query_vectors(
            vector=query_vec,
            top_k=req.top_k,
            namespace=user_id,
            metadata_filter=pinecone_filter,
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

    modality_echo = (
        "both" if pinecone_filter is None else
        ("text" if pinecone_filter.get("modality", {}).get("$eq") == "text" else "image")
    )

    return QueryResponse(
        matches=matches,
        top_k=req.top_k,
        modality_filter=modality_echo,
        namespace=user_id,
    )
