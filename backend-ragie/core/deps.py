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
def _get_supabase_admin() -> Client:
    """Get admin Supabase client (cached) - bypasses RLS for admin operations only."""
    return create_client(settings.supabase_url, settings.supabase_key)


@lru_cache(maxsize=1)
def _get_supabase_anon() -> Client:
    """Get anon Supabase client (cached) - respects RLS policies."""
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def get_supabase(current_user: AuthUser = Depends(get_current_user)) -> Client:
    """Get Supabase client respecting RLS policies.

    Uses the anon key which enforces Row-Level Security policies.
    All queries must include proper user_id filtering, which will be
    enforced at the database level through RLS policies.
    """
    return _get_supabase_anon()


def get_supabase_admin(current_user: AuthUser = Depends(get_current_user)) -> Client:
    """Get admin Supabase client (bypasses RLS).

    Use this for endpoints that implement custom authorization checks.
    Requires authentication but bypasses Row-Level Security policies.
    """
    return _get_supabase_admin()


def get_supabase_for_webhook() -> Client:
    """Get Supabase client for webhook handlers (no auth required).

    Used for endpoints that receive requests from external services (e.g., Stripe)
    where JWT authentication is not applicable.
    """
    return _get_supabase_admin()


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


def get_google_drive_service(
    supabase: Client = Depends(get_supabase_admin)
):
    """Get Google Drive service (uses admin client for write operations)."""
    from services.google_drive_service import GoogleDriveService
    return GoogleDriveService(supabase)
