"""User limits and quota management for file uploads."""

import logging
from datetime import datetime
from fastapi import HTTPException

logger = logging.getLogger(__name__)

DEFAULT_MAX_FILES = 200  # Free tier default (pages)
PREMIUM_MAX_FILES = 2000  # Premium tier (pages)
DEFAULT_MAX_MONTHLY_FILES = 50  # Free tier monthly uploads
PREMIUM_MAX_MONTHLY_FILES = 500  # Premium tier monthly uploads


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
    Sums page_count from all documents AND videos (includes both).

    Args:
        supabase: Supabase client
        user_id: User ID to check

    Returns:
        Total number of pages the user has uploaded
    """
    try:
        # Get pages from documents
        doc_response = supabase.table("ragie_documents").select(
            "page_count"
        ).eq("user_id", user_id).execute()

        doc_pages = 0
        if doc_response.data:
            # Sum page_count, treating NULL as 1 page
            doc_pages = sum(doc.get("page_count") or 1 for doc in doc_response.data)

        # Get pages from videos
        video_response = supabase.table("videos").select(
            "page_count"
        ).eq("user_id", user_id).execute()

        video_pages = 0
        if video_response.data:
            # Sum page_count from videos
            video_pages = sum(video.get("page_count") or 0 for video in video_response.data)

        return doc_pages + video_pages
    except Exception as e:
        logger.error(f"Error counting user pages: {e}")
        return 0


def get_user_max_monthly_files(supabase, user_id: str) -> int:
    """
    Get the maximum number of files a user can upload per month.
    Returns the max_monthly_files limit from user_settings, or default if not set.

    Args:
        supabase: Supabase client
        user_id: User ID to check

    Returns:
        Maximum number of files allowed per month (defaults to 50 for free tier)
    """
    try:
        response = supabase.table("user_settings").select(
            "max_monthly_files, stripe_subscription_status"
        ).eq("user_id", user_id).execute()

        if response.data and len(response.data) > 0:
            settings = response.data[0]
            max_monthly = settings.get("max_monthly_files", DEFAULT_MAX_MONTHLY_FILES)

            # Verify subscription status matches max_monthly_files
            subscription_status = settings.get("stripe_subscription_status")
            if subscription_status in ["active", "trialing"]:
                # Should be premium tier
                if max_monthly < PREMIUM_MAX_MONTHLY_FILES:
                    logger.warning(
                        f"User {user_id} has active subscription but max_monthly_files={max_monthly}, "
                        f"expected {PREMIUM_MAX_MONTHLY_FILES}"
                    )
                    return PREMIUM_MAX_MONTHLY_FILES

            return max_monthly

        # If no settings exist, return default
        return DEFAULT_MAX_MONTHLY_FILES
    except Exception as e:
        logger.error(f"Error fetching user monthly limits: {e}")
        # Return default on error to not block uploads
        return DEFAULT_MAX_MONTHLY_FILES


def get_user_monthly_file_count(supabase, user_id: str) -> int:
    """
    Get the number of files uploaded in the current month (documents + videos).
    Counts files created since the start of the current month.

    Args:
        supabase: Supabase client
        user_id: User ID to check

    Returns:
        Number of files uploaded this month
    """
    try:
        # Get current month's start date
        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Count documents uploaded this month
        doc_response = supabase.table("ragie_documents").select(
            "id", count="exact"
        ).eq("user_id", user_id).gte("created_at", month_start.isoformat()).execute()

        doc_count = doc_response.count or 0

        # Count videos uploaded this month
        video_response = supabase.table("videos").select(
            "id", count="exact"
        ).eq("user_id", user_id).gte("created_at", month_start.isoformat()).execute()

        video_count = video_response.count or 0

        return doc_count + video_count
    except Exception as e:
        logger.error(f"Error counting monthly files: {e}")
        return 0


def check_user_can_upload(supabase, user_id: str) -> dict:
    """
    Check if a user can upload another file based on their page and monthly limits.

    Args:
        supabase: Supabase client
        user_id: User ID to check

    Returns:
        Dict with can_upload (bool), current_count (int), max_files (int), remaining (int),
        monthly_count (int), max_monthly (int)

    Raises:
        HTTPException: 403 if user has reached their page limit or monthly file limit
    """
    try:
        # Get settings
        settings_response = supabase.table("user_settings").select(
            "max_files, max_monthly_files, stripe_subscription_status"
        ).eq("user_id", user_id).execute()

        if settings_response.data and len(settings_response.data) > 0:
            settings = settings_response.data[0]
            max_files = settings.get("max_files", DEFAULT_MAX_FILES)
            max_monthly = settings.get("max_monthly_files", DEFAULT_MAX_MONTHLY_FILES)
            subscription_status = settings.get("stripe_subscription_status")
            if subscription_status in ["active", "trialing"]:
                if max_files < PREMIUM_MAX_FILES:
                    logger.warning(
                        f"User {user_id} has active subscription but max_files={max_files}, "
                        f"expected {PREMIUM_MAX_FILES}"
                    )
                    max_files = PREMIUM_MAX_FILES
                if max_monthly < PREMIUM_MAX_MONTHLY_FILES:
                    max_monthly = PREMIUM_MAX_MONTHLY_FILES
        else:
            max_files = DEFAULT_MAX_FILES
            max_monthly = DEFAULT_MAX_MONTHLY_FILES

        # Get current counts
        current_page_count = get_user_file_count(supabase, user_id)
        monthly_file_count = get_user_monthly_file_count(supabase, user_id)

    except Exception as e:
        logger.error(f"Error checking upload capability: {e}")
        # Return default on error to not block uploads
        current_page_count = 0
        monthly_file_count = 0
        max_files = DEFAULT_MAX_FILES
        max_monthly = DEFAULT_MAX_MONTHLY_FILES

    # Check page quota
    page_can_upload = current_page_count < max_files
    page_remaining = max(0, max_files - current_page_count)
    page_over_limit = max(0, current_page_count - max_files)

    # Check monthly file quota
    monthly_can_upload = monthly_file_count < max_monthly
    monthly_remaining = max(0, max_monthly - monthly_file_count)

    can_upload = page_can_upload and monthly_can_upload

    if not can_upload:
        if not page_can_upload:
            if page_over_limit > 0:
                message = (
                    f"Your account has {current_page_count} pages but your current plan allows {max_files} pages. "
                    f"Please delete documents totaling {page_over_limit} page(s) before uploading new ones, or upgrade to premium."
                )
            else:
                message = (
                    f"You have reached your page upload limit of {max_files} pages. "
                    f"Upgrade your plan to upload more pages."
                )
        elif not monthly_can_upload:
            message = (
                f"You have reached your monthly file upload limit of {max_monthly} files. "
                f"You've already uploaded {monthly_file_count} files this month. Please try again next month or upgrade to premium."
            )

        raise HTTPException(
            status_code=403,
            detail={
                "error": "file_limit_reached",
                "message": message,
                "current_page_count": current_page_count,
                "max_files": max_files,
                "monthly_file_count": monthly_file_count,
                "max_monthly_files": max_monthly
            }
        )

    return {
        "can_upload": can_upload,
        "current_page_count": current_page_count,
        "max_files": max_files,
        "page_remaining": page_remaining,
        "monthly_file_count": monthly_file_count,
        "max_monthly_files": max_monthly,
        "monthly_remaining": monthly_remaining
    }


def get_user_quota_status(supabase, user_id: str) -> dict:
    """
    Get detailed quota status for a user (pages and monthly files).

    Args:
        supabase: Supabase client
        user_id: User ID to check

    Returns:
        Dict with quota information
    """
    current_page_count = get_user_file_count(supabase, user_id)
    max_files = get_user_max_files(supabase, user_id)
    monthly_file_count = get_user_monthly_file_count(supabase, user_id)
    max_monthly_files = get_user_max_monthly_files(supabase, user_id)

    # Page quota
    page_remaining = max(0, max_files - current_page_count)
    page_over_limit = max(0, current_page_count - max_files)
    page_is_over_limit = current_page_count > max_files
    page_can_upload = current_page_count < max_files
    page_percentage_used = min(100, int((current_page_count / max_files) * 100)) if max_files > 0 else 0

    # Monthly quota
    monthly_remaining = max(0, max_monthly_files - monthly_file_count)
    monthly_can_upload = monthly_file_count < max_monthly_files
    monthly_percentage_used = min(100, int((monthly_file_count / max_monthly_files) * 100)) if max_monthly_files > 0 else 0

    return {
        # Page quota
        "current_page_count": current_page_count,
        "max_pages": max_files,
        "page_remaining": page_remaining,
        "page_over_limit": page_over_limit,
        "page_is_over_limit": page_is_over_limit,
        "page_can_upload": page_can_upload,
        "page_percentage_used": page_percentage_used,
        # Monthly file quota
        "monthly_file_count": monthly_file_count,
        "max_monthly_files": max_monthly_files,
        "monthly_remaining": monthly_remaining,
        "monthly_can_upload": monthly_can_upload,
        "monthly_percentage_used": monthly_percentage_used,
        # Overall
        "can_upload": page_can_upload and monthly_can_upload
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
                "max_files": DEFAULT_MAX_FILES,
                "max_monthly_files": DEFAULT_MAX_MONTHLY_FILES
            }).execute()
            logger.info(f"Created default settings for user {user_id}")
    except Exception as e:
        logger.error(f"Error ensuring user settings: {e}")
