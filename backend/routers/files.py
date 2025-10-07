# app/api/routes/files.py
from typing import Optional, Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from core.security import get_current_user, AuthUser
from core.deps import get_supabase

router = APIRouter(prefix="/files", tags=["files"])

SortField = Literal["created_at", "size", "name"]
SortDir = Literal["asc", "desc"]
GroupSort = Literal["none", "group_then_time"]

class FileItem(BaseModel):
    doc_id: str
    user_id: str
    filename: str
    bucket: str
    storage_path: str
    mime_type: str
    modality: str
    size_bytes: Optional[int] = None
    chunk_count: int
    created_at: str
    # NEW (from app_docs_with_group view; may be null)
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    group_sort_index: Optional[int] = None

class FilesResponse(BaseModel):
    items: list[FileItem]
    page: int
    page_size: int
    total: int
    has_next: bool


@router.get("", response_model=FilesResponse)
def list_files(
    q: Optional[str] = Query(None, description="search in filename (case-insensitive)"),

    # ✅ broadened to allow audio / video or any other string
    modality: Optional[str] = Query(
        None,
        description="Filter by modality such as text, image, audio, video"
    ),

    created_from: Optional[str] = Query(None, description="ISO date or timestamp"),
    created_to: Optional[str] = Query(None, description="ISO date or timestamp"),

    min_size: Optional[int] = Query(None, ge=0),
    max_size: Optional[int] = Query(None, ge=0),

    sort: SortField = Query("created_at"),
    dir: SortDir = Query("desc"),

    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),

    recent: Optional[bool] = Query(
        None, description="shortcut for sort=created_at desc"
    ),

    # NEW
    group_id: Optional[str] = Query(None, description="filter by group"),
    group_sort: GroupSort = Query(
        "none",
        description="group_then_time = order by group then created_at desc"
    ),

    auth: AuthUser = Depends(get_current_user),
    supabase = Depends(get_supabase),
):
    user_id = auth.id
    if recent:
        sort, dir = "created_at", "desc"

    # Choose base: always use augmented view
    base_table = "app_docs_with_group"

    sb = supabase.table(base_table).select("*", count="exact").eq("user_id", user_id)

    if q:
        sb = sb.ilike("filename", f"%{q}%")
    if modality:
        sb = sb.eq("modality", modality)
    if created_from:
        sb = sb.gte("created_at", created_from)
    if created_to:
        sb = sb.lte("created_at", created_to)
    if min_size is not None:
        sb = sb.gte("size_bytes", min_size)
    if max_size is not None:
        sb = sb.lte("size_bytes", max_size)

    # 👇 handle group filter (UUID or "No Group")
    if group_id is not None:
        if group_id == "":
            sb = sb.is_("group_id", None)   # only ungrouped
        else:
            sb = sb.eq("group_id", group_id)

    if group_sort == "group_then_time":
        sb = sb.order("group_sort_index", desc=False, nullsfirst=True) \
               .order("created_at", desc=True)
    else:
        order_col = {"name": "filename", "size": "size_bytes"}.get(sort, "created_at")
        sb = sb.order(order_col, desc=(dir == "desc"))

    start = (page - 1) * page_size
    end = start + page_size - 1
    sb = sb.range(start, end)

    resp = sb.execute()
    items = resp.data or []
    total = getattr(resp, "count", None) or 0

    return FilesResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        has_next=(start + len(items)) < total,
    )
