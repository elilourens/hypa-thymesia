"""User limits and quota management for file uploads."""

import logging
from fastapi import HTTPException

logger = logging.getLogger(__name__)

DEFAULT_MAX_FILES = 200  # Free tier default (pages)
PREMIUM_MAX_FILES = 2000  # Premium tier (pages)


def get_user_max_files(supabase, user_id: str) -> int:
    """
    Get the maximum number of pages a user can upload.
    Returns the max_files limit from user_settings, or default if not set.

    Args:
        supabase: Supabase client
        user_id: User ID to check

    Returns:
        Maximum number of pages allowed (defaults to 200 for free tier)
    """
    try:
        response = supabase.table("user_settings").select(
            "max_files, stripe_subscription_status"
        ).eq("user_id", user_id).execute()

        if response.data and len(response.data) > 0:
            settings = response.data[0]
            max_files = settings.get("max_files", DEFAULT_MAX_FILES)

            # Verify subscription status matches max_files
            subscription_status = settings.get("stripe_subscription_status")
            if subscription_status in ["active", "trialing"]:
                # Should be premium tier
                if max_files < PREMIUM_MAX_FILES:
                    logger.warning(
                        f"User {user_id} has active subscription but max_files={max_files}, "
                        f"expected {PREMIUM_MAX_FILES}"
                    )
                    return PREMIUM_MAX_FILES

            return max_files

        # If no settings exist, return default
        return DEFAULT_MAX_FILES
    except Exception as e:
        logger.error(f"Error fetching user limits: {e}")
        # Return default on error to not block uploads
        return DEFAULT_MAX_FILES


def get_user_file_count(supabase, user_id: str) -> int:
    """
    Get the current number of pages a user has uploaded.
    Sums page_count from all documents, treating NULL as 1 page.

    Args:
        supabase: Supabase client
        user_id: User ID to check

    Returns:
        Total number of pages the user has uploaded
    """
    try:
        response = supabase.table("ragie_documents").select(
            "page_count"
        ).eq("user_id", user_id).execute()

        if not response.data:
            return 0

        # Sum page_count, treating NULL as 1 page
        total_pages = sum(doc.get("page_count") or 1 for doc in response.data)
        return total_pages
    except Exception as e:
        logger.error(f"Error counting user pages: {e}")
        return 0


def check_user_can_upload(supabase, user_id: str) -> dict:
    """
    Check if a user can upload another file based on their limit.

    Args:
        supabase: Supabase client
        user_id: User ID to check

    Returns:
        Dict with can_upload (bool), current_count (int), max_files (int), remaining (int)

    Raises:
        HTTPException: 403 if user has reached their limit
    """
    try:
        # Get both file count and user limits in parallel requests
        file_count_response = supabase.table("ragie_documents").select(
            "id", count="exact"
        ).eq("user_id", user_id).execute()

        settings_response = supabase.table("user_settings").select(
            "max_files, stripe_subscription_status"
        ).eq("user_id", user_id).execute()

        current_count = file_count_response.count or 0

        if settings_response.data and len(settings_response.data) > 0:
            settings = settings_response.data[0]
            max_files = settings.get("max_files", DEFAULT_MAX_FILES)
            subscription_status = settings.get("stripe_subscription_status")
            if subscription_status in ["active", "trialing"]:
                if max_files < PREMIUM_MAX_FILES:
                    logger.warning(
                        f"User {user_id} has active subscription but max_files={max_files}, "
                        f"expected {PREMIUM_MAX_FILES}"
                    )
                    max_files = PREMIUM_MAX_FILES
        else:
            max_files = DEFAULT_MAX_FILES
    except Exception as e:
        logger.error(f"Error checking upload capability: {e}")
        # Return default on error to not block uploads
        current_count = 0
        max_files = DEFAULT_MAX_FILES

    can_upload = current_count < max_files
    remaining = max(0, max_files - current_count)
    over_limit = max(0, current_count - max_files)

    if not can_upload:
        if over_limit > 0:
            message = (
                f"Your account has {current_count} pages but your current plan allows {max_files} pages. "
                f"Please delete documents totaling {over_limit} page(s) before uploading new ones, or upgrade to premium."
            )
        else:
            message = (
                f"You have reached your page upload limit of {max_files} pages. "
                f"Upgrade your plan to upload more pages."
            )

        raise HTTPException(
            status_code=403,
            detail={
                "error": "file_limit_reached",
                "message": message,
                "current_count": current_count,
                "max_files": max_files,
                "remaining": 0,
                "over_limit": over_limit
            }
        )

    return {
        "can_upload": can_upload,
        "current_count": current_count,
        "max_files": max_files,
        "remaining": remaining
    }


def get_user_quota_status(supabase, user_id: str) -> dict:
    """
    Get detailed quota status for a user.

    Args:
        supabase: Supabase client
        user_id: User ID to check

    Returns:
        Dict with quota information
    """
    current_count = get_user_file_count(supabase, user_id)
    max_files = get_user_max_files(supabase, user_id)

    remaining = max(0, max_files - current_count)
    over_limit = max(0, current_count - max_files)
    is_over_limit = current_count > max_files
    can_upload = current_count < max_files
    percentage_used = min(100, int((current_count / max_files) * 100)) if max_files > 0 else 0

    return {
        "current_count": current_count,
        "max_files": max_files,
        "remaining": remaining,
        "over_limit": over_limit,
        "is_over_limit": is_over_limit,
        "can_upload": can_upload,
        "percentage_used": percentage_used
    }


def ensure_user_settings_exist(supabase, user_id: str) -> None:
    """Ensure user_settings record exists for a user."""
    try:
        response = supabase.table("user_settings").select(
            "user_id"
        ).eq("user_id", user_id).execute()

        if not response.data or len(response.data) == 0:
            supabase.table("user_settings").insert({
                "user_id": user_id,
                "max_files": DEFAULT_MAX_FILES
            }).execute()
            logger.info(f"Created default settings for user {user_id}")
    except Exception as e:
        logger.error(f"Error ensuring user settings: {e}")
