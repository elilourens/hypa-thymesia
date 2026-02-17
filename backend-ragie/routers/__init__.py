"""API routers module."""

from .health import router as health_router
from .documents import router as documents_router
from .search import router as search_router
from .groups import router as groups_router
from .stripe_payments import router as stripe_router
from .user_settings import router as user_settings_router
from .audit import router as audit_router
from .storage import router as storage_router
from .videos import router as videos_router
from .ragie_webhooks import router as ragie_webhooks_router
from .google_drive import router as google_drive_router
from .api_keys import router as api_keys_router

__all__ = [
    "health_router",
    "documents_router",
    "search_router",
    "groups_router",
    "stripe_router",
    "user_settings_router",
    "audit_router",
    "storage_router",
    "videos_router",
    "ragie_webhooks_router",
    "google_drive_router",
    "api_keys_router",
]
