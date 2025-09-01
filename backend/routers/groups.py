from typing import Optional, List, Literal, Dict
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from core.security import get_current_user, AuthUser
from core.deps import get_supabase

router = APIRouter(prefix="/groups", tags=["groups"])

# ---------------- Models ----------------

class GroupIn(BaseModel):
    name: str
    sort_index: int = 0

class GroupOut(BaseModel):
    group_id: str
    user_id: str
    name: str
    sort_index: int

class GroupRename(BaseModel):
    name: str

class GroupPatch(BaseModel):
    # UUID or name; None clears the group
    group: Optional[str] = None

# -------------- Helpers -----------------

def _resolve_group_id(supabase, *, user_id: str, group_input: Optional[str]) -> Optional[str]:
    """
    Accept either a UUID or a name. If a name is given and the group doesn't exist,
    create it and return the new UUID. Returns None if group_input is falsy.
    """
    if not group_input:
        return None

    # Try UUID
    try:
        _ = UUID(group_input)
        res = supabase.table("app_groups") \
            .select("group_id") \
            .eq("group_id", group_input) \
            .eq("user_id", user_id) \
            .limit(1).execute()
        if not res.data:
            raise HTTPException(404, detail="Group not found or not owned by user")
        return group_input
    except Exception:
        # Treat as name
        name = group_input.strip()
        if not name:
            return None

        found = supabase.table("app_groups") \
            .select("group_id") \
            .eq("user_id", user_id) \
            .eq("name", name) \
            .limit(1).execute()
        if found.data:
            return found.data[0]["group_id"]

        created = supabase.table("app_groups").insert({
            "user_id": user_id,
            "name": name,
            # sort_index defaults to 0; client can PATCH later to reorder
        }).execute()
        if not created.data:
            raise HTTPException(500, detail="Failed to create group")
        return created.data[0]["group_id"]

def _sync_pinecone_group_metadata(
    *,
    supabase,
    user_id: str,
    doc_id: str,
    group_id: Optional[str],
) -> None:
    """
    Update Pinecone metadata for all vectors belonging to this doc:
      - set group_id to the new value, or
      - delete group_id key if clearing.
    """
    # Get chunks for this doc to determine modalities
    chunks_resp = supabase.table("app_chunks") \
        .select("chunk_id, modality") \
        .eq("doc_id", doc_id) \
        .eq("user_id", user_id) \
        .execute()
    chunks = chunks_resp.data or []
    if not chunks:
        return

    chunk_ids = [c["chunk_id"] for c in chunks]
    mod_map: Dict[str, str] = {c["chunk_id"]: c["modality"] for c in chunks}

    regs_resp = supabase.table("app_vector_registry") \
        .select("vector_id, chunk_id") \
        .in_("chunk_id", chunk_ids).execute()
    regs = regs_resp.data or []
    if not regs:
        return

    # Group vector IDs by modality to hit the right Pinecone index
    by_mod: Dict[str, List[str]] = {}
    for r in regs:
        m = mod_map.get(r["chunk_id"], "text")
        by_mod.setdefault(m, []).append(r["vector_id"])

    from data_upload.pinecone_services import update_vectors_metadata

    for modality, vector_ids in by_mod.items():
        if not vector_ids:
            continue
        if group_id:
            update_vectors_metadata(
                vector_ids=vector_ids,
                modality=modality,         # "text" | "image" | "clip_text"
                namespace=user_id,         # tenant isolation
                set_metadata={"group_id": group_id},
            )
        else:
            update_vectors_metadata(
                vector_ids=vector_ids,
                modality=modality,
                namespace=user_id,
                delete_keys=["group_id"],
            )

# -------------- Group CRUD ----------------

@router.post("", response_model=GroupOut)
def create_group(
    payload: GroupIn,
    auth: AuthUser = Depends(get_current_user),
    supabase = Depends(get_supabase),
):
    user_id = auth.id
    res = supabase.table("app_groups").insert({
        "user_id": user_id,
        "name": payload.name,
        "sort_index": payload.sort_index
    }).execute()
    if not res.data:
        raise HTTPException(500, "Failed to create group")
    return res.data[0]

@router.get("", response_model=List[GroupOut])
def list_groups(
    auth: AuthUser = Depends(get_current_user),
    supabase = Depends(get_supabase),
):
    user_id = auth.id
    res = supabase.table("app_groups").select("*") \
        .eq("user_id", user_id) \
        .order("sort_index", desc=False) \
        .execute()
    return res.data or []

@router.patch("/{group_id}", response_model=GroupOut)
def rename_group(
    group_id: str,
    payload: GroupRename,
    auth: AuthUser = Depends(get_current_user),
    supabase = Depends(get_supabase),
):
    user_id = auth.id
    res = supabase.table("app_groups").update({"name": payload.name}) \
        .eq("group_id", group_id) \
        .eq("user_id", user_id) \
        .execute()
    if not res.data:
        raise HTTPException(404, "Group not found")
    return res.data[0]

@router.delete("/{group_id}")
def delete_group(
    group_id: str,
    auth: AuthUser = Depends(get_current_user),
    supabase = Depends(get_supabase),
):
    user_id = auth.id
    # FK on app_doc_meta.group_id is ON DELETE SET NULL, so vectors keep working;
    # if you also want to clear Pinecone metadata for affected docs, do a follow-up job.
    res = supabase.table("app_groups").delete() \
        .eq("group_id", group_id) \
        .eq("user_id", user_id) \
        .execute()
    if not res.data:
        raise HTTPException(404, "Group not found")
    return {"ok": True}

# -------------- Assign / Clear doc group (this is what you asked for) --------------

@router.put("/docs/{doc_id}/group")
def set_doc_group(
    doc_id: str,
    payload: GroupPatch = Body(...),
    auth: AuthUser = Depends(get_current_user),
    supabase = Depends(get_supabase),
):
    """
    Assign a document to a group, or clear it.

    Body:
      { "group": "<uuid-or-name>" }  -> assign to that group (creates by name if needed)
      { "group": null }              -> clear the group
    """
    user_id = auth.id

    # Ensure the doc exists and belongs to the user
    doc = supabase.table("app_docs").select("doc_id") \
        .eq("doc_id", doc_id) \
        .eq("user_id", user_id) \
        .limit(1).execute()
    if not doc.data:
        raise HTTPException(404, "Doc not found")

    gid = _resolve_group_id(supabase, user_id=user_id, group_input=payload.group)

    # Upsert SQL metadata
    supabase.table("app_doc_meta").upsert(
        {"doc_id": doc_id, "user_id": user_id, "group_id": gid},
        on_conflict="doc_id",
    ).execute()

    # Sync Pinecone metadata on all vectors of this doc
    _sync_pinecone_group_metadata(
        supabase=supabase,
        user_id=user_id,
        doc_id=doc_id,
        group_id=gid,
    )

    return {"ok": True, "group_id": gid}
