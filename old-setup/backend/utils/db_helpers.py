"""Shared database helper utilities for Supabase operations."""

import hashlib
from typing import Optional, List, Dict, Any
from supabase import Client


def ensure_doc_meta(
    supabase: Client,
    *,
    user_id: str,
    doc_id: str,
    group_id: Optional[str]
) -> None:
    """
    Ensure app_doc_meta row exists.
    app_docs is a VIEW; persist group ownership in app_doc_meta.
    """
    supabase.table("app_doc_meta").upsert(
        {"doc_id": doc_id, "user_id": user_id, "group_id": group_id},
        on_conflict="doc_id",
    ).execute()


def register_vectors(supabase: Client, rows: List[Dict[str, Any]]) -> None:
    """Register vectors in app_vector_registry table."""
    if rows:
        supabase.table("app_vector_registry").upsert(rows).execute()


def sha256_hash(data: bytes | str) -> str:
    """Generate SHA256 hash for bytes or string data."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()
