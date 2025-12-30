"""
User limits and quota management for file uploads.
"""
import logging
from typing import Optional
from fastapi import HTTPException

logger = logging.getLogger(__name__)

DEFAULT_MAX_FILES = 50  # Free tier default
PREMIUM_MAX_FILES = 100  # Premium tier (£2.99/month)


def get_user_max_files(supabase, user_id: str) -> int:
    """
    Get the maximum number of files a user can upload.
    Returns the max_files limit from user_settings, or default if not set.

    The max_files value is automatically set based on subscription status:
    - Free tier: 50 files
    - Premium tier (£2.99/month): 100 files

    Args:
        supabase: Supabase client
        user_id: User ID to check

    Returns:
        Maximum number of files allowed (defaults to 50 for free tier)
    """
    try:
        response = supabase.table("user_settings").select("max_files, stripe_subscription_status").eq("user_id", user_id).execute()

        if response.data and len(response.data) > 0:
            settings = response.data[0]
            max_files = settings.get("max_files", DEFAULT_MAX_FILES)

            # Verify subscription status matches max_files
            # This is a safety check in case of data inconsistency
            subscription_status = settings.get("stripe_subscription_status")
            if subscription_status in ["active", "trialing"]:
                # Should be premium tier
                if max_files < PREMIUM_MAX_FILES:
                    logger.warning(f"User {user_id} has active subscription but max_files={max_files}, expected {PREMIUM_MAX_FILES}")
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
    Get the current number of files (documents) a user has uploaded.

    Args:
        supabase: Supabase client
        user_id: User ID to check

    Returns:
        Number of documents the user currently has
    """
    try:
        response = supabase.table("app_doc_meta").select("doc_id", count="exact").eq("user_id", user_id).execute()
        return response.count or 0
    except Exception as e:
        logger.error(f"Error counting user files: {e}")
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
    current_count = get_user_file_count(supabase, user_id)
    max_files = get_user_max_files(supabase, user_id)

    can_upload = current_count < max_files
    remaining = max_files - current_count

    if not can_upload:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "file_limit_reached",
                "message": f"You have reached your file upload limit of {max_files} files. Upgrade your plan to upload more files.",
                "current_count": current_count,
                "max_files": max_files,
                "remaining": 0
            }
        )

    return {
        "can_upload": True,
        "current_count": current_count,
        "max_files": max_files,
        "remaining": remaining
    }


def ensure_user_settings_exist(supabase, user_id: str) -> None:
    """
    Ensure user_settings record exists for a user.
    Creates one with defaults if it doesn't exist.

    Args:
        supabase: Supabase client
        user_id: User ID to ensure settings for
    """
    try:
        # Check if settings exist
        response = supabase.table("user_settings").select("user_id").eq("user_id", user_id).execute()

        if not response.data or len(response.data) == 0:
            # Create default settings
            supabase.table("user_settings").insert({
                "user_id": user_id,
                "max_files": DEFAULT_MAX_FILES
            }).execute()
            logger.info(f"Created default settings for user {user_id}")
    except Exception as e:
        logger.error(f"Error ensuring user settings: {e}")
        # Don't raise - this is best effort
