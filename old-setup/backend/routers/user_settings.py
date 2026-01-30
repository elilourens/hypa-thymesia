"""
User settings management endpoints.
Handles quota information and upgrade management.
"""
import logging
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException

from core.deps import get_supabase
from core.security import get_current_user, AuthUser
from core.user_limits import (
    get_user_file_count,
    get_user_max_files,
    get_user_quota_status,
    ensure_user_settings_exist,
    DEFAULT_MAX_FILES
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/user", tags=["user_settings"])


class UserQuotaResponse(BaseModel):
    """User file quota information"""
    current_count: int
    max_files: int
    remaining: int
    over_limit: int
    is_over_limit: bool
    can_upload: bool
    percentage_used: int


class UpdateMaxFilesRequest(BaseModel):
    """Request to update user's max files limit"""
    max_files: int


@router.get("/quota", response_model=UserQuotaResponse)
def get_user_quota(
    auth: AuthUser = Depends(get_current_user),
    supabase = Depends(get_supabase),
):
    """
    Get the current user's file quota information.
    Shows how many files they have, their limit, remaining quota,
    and whether they're over their limit (e.g., after downgrading from premium).
    """
    user_id = auth.id

    # Ensure settings exist
    ensure_user_settings_exist(supabase, user_id)

    # Get comprehensive quota status
    quota = get_user_quota_status(supabase, user_id)

    return UserQuotaResponse(**quota)


@router.patch("/max-files")
def update_user_max_files(
    request: UpdateMaxFilesRequest,
    auth: AuthUser = Depends(get_current_user),
    supabase = Depends(get_supabase),
):
    """
    Update a user's maximum file limit.

    This endpoint would typically be called after payment processing
    to upgrade a user's plan (50 -> 100 -> 200 files, etc.).

    For production, you should:
    1. Verify payment/subscription status before calling this
    2. Add admin-only authentication or integrate with your payment provider
    3. Add audit logging for plan changes
    """
    user_id = auth.id

    # Validate the new limit
    if request.max_files < 0:
        raise HTTPException(
            status_code=400,
            detail="max_files must be non-negative"
        )

    # Minimum should be at least the default free tier
    if request.max_files < DEFAULT_MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"max_files cannot be less than the default limit of {DEFAULT_MAX_FILES}"
        )

    try:
        # Ensure settings record exists
        ensure_user_settings_exist(supabase, user_id)

        # Update the limit
        response = supabase.table("user_settings").update({
            "max_files": request.max_files
        }).eq("user_id", user_id).execute()

        if not response.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to update user settings"
            )

        logger.info(f"Updated max_files for user {user_id} to {request.max_files}")

        # Return updated quota info
        current_count = get_user_file_count(supabase, user_id)
        remaining = max(0, request.max_files - current_count)
        percentage_used = (current_count / request.max_files * 100) if request.max_files > 0 else 0

        return {
            "success": True,
            "message": f"File limit updated to {request.max_files}",
            "quota": {
                "current_count": current_count,
                "max_files": request.max_files,
                "remaining": remaining,
                "percentage_used": round(percentage_used, 2)
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating max_files: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to update file limit"
        )
