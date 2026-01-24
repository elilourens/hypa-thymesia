"""Dependency injection container for services and clients."""

from functools import lru_cache
from supabase import create_client, Client
from ragie import Ragie
from core.config import settings
from core.security import get_current_user, AuthUser
from fastapi import Depends
from services.ragie_service import RagieService
from services.supabase_service import SupabaseService


@lru_cache(maxsize=1)
def _get_supabase_base() -> Client:
    """Get base Supabase client (cached singleton)."""
    return create_client(settings.supabase_url, settings.supabase_key)


def get_supabase(current_user: AuthUser = Depends(get_current_user)) -> Client:
    """Get Supabase client with user's JWT token for RLS policies."""
    client = _get_supabase_base()
    # Set the user's JWT token so auth.uid() in RLS policies returns the user's ID
    client.auth.set_session(current_user.token, "")
    return client


@lru_cache(maxsize=1)
def get_ragie_client() -> Ragie:
    """Get Ragie client (cached singleton)."""
    return Ragie(auth=settings.ragie_api_key)


@lru_cache(maxsize=1)
def get_ragie_service() -> RagieService:
    """Get Ragie service wrapper."""
    return RagieService(get_ragie_client())


def get_supabase_service(supabase: Client = Depends(get_supabase)) -> SupabaseService:
    """Get Supabase service wrapper with user context."""
    return SupabaseService(supabase)
