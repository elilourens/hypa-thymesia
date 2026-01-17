"""
User limits and quota management for file uploads.
"""
import logging
from typing import Optional
from fastapi import HTTPException

logger = logging.getLogger(__name__)

DEFAULT_MAX_FILES = 50  # Free tier default
PREMIUM_MAX_FILES = 100  # Premium tier (£2.99/month)
MINUTES_PER_TOKEN = 5  # 5 minutes of video = 1 file token


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


def calculate_video_tokens(duration_seconds: float) -> int:
    """
    Calculate the number of file tokens a video consumes based on its duration.

    Args:
        duration_seconds: Video duration in seconds

    Returns:
        Number of file tokens (minimum 1)
    """
    import math
    if duration_seconds <= 0:
        return 1
    return max(1, math.ceil(duration_seconds / (MINUTES_PER_TOKEN * 60)))


def get_user_file_count(supabase, user_id: str) -> int:
    """
    Get the current number of file tokens a user has consumed.
    This replaces simple file counting with token-based counting.

    For videos: tokens are calculated based on duration (5 minutes = 1 token)
    For other files: 1 token per file (default)

    Args:
        supabase: Supabase client
        user_id: User ID to check

    Returns:
        Total number of file tokens the user has consumed
    """
    try:
        # Query all documents and sum their file_tokens
        response = supabase.table("app_doc_meta").select("file_tokens").eq("user_id", user_id).execute()

        if not response.data:
            return 0

        # Sum all file_tokens (default is 1 per file, higher for long videos)
        total_tokens = sum(doc.get("file_tokens", 1) for doc in response.data)
        return total_tokens
    except Exception as e:
        logger.error(f"Error counting user file tokens: {e}")
        return 0


def check_user_can_upload_video(supabase, user_id: str, duration_seconds: float) -> dict:
    """
    Check if a user can upload a video based on its duration and their token limit.

    Args:
        supabase: Supabase client
        user_id: User ID to check
        duration_seconds: Duration of the video in seconds

    Returns:
        Dict with can_upload (bool), current_count (int), max_files (int),
        tokens_needed (int), remaining (int)

    Raises:
        HTTPException: 403 if user doesn't have enough tokens remaining
    """
    current_count = get_user_file_count(supabase, user_id)
    max_files = get_user_max_files(supabase, user_id)
    tokens_needed = calculate_video_tokens(duration_seconds)

    can_upload = (current_count + tokens_needed) <= max_files
    remaining = max(0, max_files - current_count)

    if not can_upload:
        # User doesn't have enough tokens
        message = (
            f"This video requires {tokens_needed} file token(s) ({duration_seconds / 60:.1f} minutes), "
            f"but you only have {remaining} token(s) remaining. "
            f"Your current usage is {current_count}/{max_files} tokens. "
            f"Please delete some files or upgrade to premium to upload this video."
        )

        raise HTTPException(
            status_code=403,
            detail={
                "error": "file_limit_reached",
                "message": message,
                "current_count": current_count,
                "max_files": max_files,
                "tokens_needed": tokens_needed,
                "remaining": remaining,
                "over_limit": tokens_needed - remaining
            }
        )

    return {
        "can_upload": True,
        "current_count": current_count,
        "max_files": max_files,
        "tokens_needed": tokens_needed,
        "remaining": remaining
    }


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
    remaining = max(0, max_files - current_count)  # Ensure remaining is never negative
    over_limit = max(0, current_count - max_files)  # How many files over the limit

    if not can_upload:
        # Determine appropriate message based on whether they're over limit
        if over_limit > 0:
            # User downgraded and is over their limit
            message = (
                f"Your account has {current_count} files but your current plan allows {max_files} files. "
                f"Please delete {over_limit} file(s) before uploading new ones, or upgrade to premium to access more storage."
            )
        else:
            # User is at exactly their limit
            message = f"You have reached your file upload limit of {max_files} files. Upgrade your plan to upload more files."

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
        "can_upload": True,
        "current_count": current_count,
        "max_files": max_files,
        "remaining": remaining
    }


def get_user_quota_status(supabase, user_id: str) -> dict:
    """
    Get detailed quota status for a user, including whether they're over their limit.
    This is useful for displaying warnings/notifications in the UI.

    Args:
        supabase: Supabase client
        user_id: User ID to check

    Returns:
        Dict with:
        - current_count: Number of files currently stored
        - max_files: Maximum files allowed on current plan
        - remaining: Files remaining (0 if over limit)
        - over_limit: Number of files over the limit (0 if under)
        - is_over_limit: Boolean indicating if user exceeded their quota
        - can_upload: Boolean indicating if new uploads are allowed
        - percentage_used: Percentage of quota used (capped at 100)
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
