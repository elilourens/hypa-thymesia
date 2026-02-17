"""API key generation and validation for MCP access."""

import hashlib
import logging
import secrets
from typing import Optional

logger = logging.getLogger(__name__)

KEY_PREFIX = "hypa_"
KEY_DISPLAY_LENGTH = 12  # e.g. "hypa_ab12cd34"


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns:
        (full_key, key_prefix, key_hash)
        - full_key: returned to user once, never stored
        - key_prefix: first 12 chars shown in UI (e.g. "hypa_ab12cd")
        - key_hash: SHA-256 of full_key, stored in DB
    """
    raw = secrets.token_urlsafe(32)
    full_key = f"{KEY_PREFIX}{raw}"
    key_prefix = full_key[:KEY_DISPLAY_LENGTH]
    key_hash = _hash_key(full_key)
    return full_key, key_prefix, key_hash


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def validate_api_key(token: str, supabase) -> Optional[str]:
    """Validate an API key token and return the user_id, or None if invalid.

    Args:
        token: The raw Bearer token from the Authorization header
        supabase: Admin Supabase client (bypasses RLS for key lookup)

    Returns:
        user_id string if valid and active, else None
    """
    if not token.startswith(KEY_PREFIX):
        return None

    key_hash = _hash_key(token)

    try:
        result = (
            supabase.table("user_api_keys")
            .select("id, user_id")
            .eq("key_hash", key_hash)
            .eq("is_active", True)
            .single()
            .execute()
        )
    except Exception:
        return None

    if not result.data:
        return None

    # Fire-and-forget usage tracking update (best effort)
    try:
        supabase.rpc("increment_api_key_usage", {"key_id": result.data["id"]}).execute()
    except Exception as e:
        logger.warning(f"Failed to update API key usage: {e}")

    return result.data["user_id"]
