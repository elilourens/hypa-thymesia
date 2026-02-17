"""API key management endpoints for MCP access."""

import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from supabase import Client

from core import get_current_user, AuthUser
from core.deps import get_supabase_admin
from core.api_key_auth import generate_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class ApiKeyCreate(BaseModel):
    name: str


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    is_active: bool
    use_count: int = 0


class ApiKeyCreateResponse(ApiKeyResponse):
    key: str  # Full key — returned once only


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_admin),
):
    """List all API keys for the current user (keys are masked)."""
    result = (
        supabase.table("user_api_keys")
        .select("id, name, key_prefix, created_at, last_used_at, is_active, use_count")
        .eq("user_id", current_user.id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


@router.post("", response_model=ApiKeyCreateResponse, status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_admin),
):
    """Create a new API key. The full key is returned once and never stored."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name must not be empty")

    # Limit keys per user
    count_result = (
        supabase.table("user_api_keys")
        .select("id", count="exact")
        .eq("user_id", current_user.id)
        .eq("is_active", True)
        .execute()
    )
    if (count_result.count or 0) >= 10:
        raise HTTPException(status_code=400, detail="Maximum of 10 active API keys allowed")

    full_key, key_prefix, key_hash = generate_api_key()

    result = (
        supabase.table("user_api_keys")
        .insert({
            "user_id": current_user.id,
            "name": name,
            "key_prefix": key_prefix,
            "key_hash": key_hash,
        })
        .execute()
    )

    row = result.data[0]
    return ApiKeyCreateResponse(
        id=row["id"],
        name=row["name"],
        key_prefix=row["key_prefix"],
        created_at=row["created_at"],
        last_used_at=row.get("last_used_at"),
        is_active=row["is_active"],
        key=full_key,
    )


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_admin),
):
    """Revoke (soft-delete) an API key."""
    result = (
        supabase.table("user_api_keys")
        .delete()
        .eq("id", key_id)
        .eq("user_id", current_user.id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="API key not found")
