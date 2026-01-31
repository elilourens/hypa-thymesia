"""User settings endpoints."""

import logging
from fastapi import APIRouter, Depends, HTTPException

from supabase import Client
from core import get_current_user, AuthUser
from core.deps import get_supabase
from core.user_limits import get_user_quota_status, ensure_user_settings_exist
from schemas import UserSettings, UserQuotaStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/user-settings", tags=["user-settings"])


@router.get("", response_model=UserSettings)
async def get_user_settings(
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Get user settings."""
    try:
        # Ensure settings exist
        ensure_user_settings_exist(supabase, current_user.id)

        response = supabase.table("user_settings").select(
            "*"
        ).eq("user_id", current_user.id).single().execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="User settings not found")

        settings = response.data
        return UserSettings(
            user_id=settings["user_id"],
            stripe_customer_id=settings.get("stripe_customer_id"),
            stripe_subscription_id=settings.get("stripe_subscription_id"),
            stripe_subscription_status=settings.get("stripe_subscription_status"),
            stripe_current_period_end=settings.get("stripe_current_period_end"),
            stripe_cancel_at_period_end=settings.get("stripe_cancel_at_period_end", False),
            max_files=settings.get("max_files", 50),
            created_at=settings["created_at"],
            updated_at=settings["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user settings")


@router.get("/quota-status")
async def get_quota_status(
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Get user quota status (pages and monthly files)."""
    try:
        quota_status = get_user_quota_status(supabase, current_user.id)
        return quota_status

    except Exception as e:
        logger.error(f"Error getting quota status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get quota status")
