"""Core module for configuration, security, and dependencies."""

from core.config import settings
from core.security import get_current_user, AuthUser
from core.deps import get_supabase, get_ragie_client, get_ragie_service, get_supabase_service

__all__ = [
    "settings",
    "get_current_user",
    "AuthUser",
    "get_supabase",
    "get_ragie_client",
    "get_ragie_service",
    "get_supabase_service",
]
