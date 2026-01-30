"""User limits and quota management for file uploads."""

import logging
from datetime import datetime
from fastapi import HTTPException

logger = logging.getLogger(__name__)

DEFAULT_MAX_FILES = 200  # Free tier default (pages)
PREMIUM_MAX_FILES = 2000  # Premium tier (pages)
DEFAULT_MAX_MONTHLY_FILES = 50  # Free tier monthly uploads
PREMIUM_MAX_MONTHLY_FILES = 500  # Premium tier monthly uploads
DEFAULT_MAX_MONTHLY_THROUGHPUT = 5 * 1024**3  # 5 GB in bytes for free tier
PREMIUM_MAX_MONTHLY_THROUGHPUT = 20 * 1024**3  # 20 GB in bytes for premium


def _get_user_settings_once(supabase, user_id: str) -> dict:
    """
    Fetch user settings with all quota-related fields in a single query.
    Internal helper to avoid duplicate queries to user_settings table.

    Args:
        supabase: Supabase client
        user_id: User ID to check

    Returns:
        Dict with keys: max_files, max_monthly_files, subscription_status
    """
    try:
        response = supabase.table("user_settings").select(
            "max_files, max_monthly_files, stripe_subscription_status"
        ).eq("user_id", user_id).execute()

        if response.data and len(response.data) > 0:
            settings = response.data[0]
            max_files = settings.get("max_files", DEFAULT_MAX_FILES)
            max_monthly = settings.get("max_monthly_files", DEFAULT_MAX_MONTHLY_FILES)
            subscription_status = settings.get("stripe_subscription_status")

            # Adjust for premium subscriptions
            if subscription_status in ["active", "trialing"]:
                if max_files < PREMIUM_MAX_FILES:
                    max_files = PREMIUM_MAX_FILES
                if max_monthly < PREMIUM_MAX_MONTHLY_FILES:
                    max_monthly = PREMIUM_MAX_MONTHLY_FILES

            return {
                "max_files": max_files,
                "max_monthly_files": max_monthly,
                "subscription_status": subscription_status
            }

        return {
            "max_files": DEFAULT_MAX_FILES,
            "max_monthly_files": DEFAULT_MAX_MONTHLY_FILES,
            "subscription_status": None
        }
    except Exception as e:
        logger.error(f"Error fetching user settings: {e}")
        return {
            "max_files": DEFAULT_MAX_FILES,
            "max_monthly_files": DEFAULT_MAX_MONTHLY_FILES,
            "subscription_status": None
        }


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
    Sums page_count from all documents (includes videos stored in ragie_documents).

    Args:
        supabase: Supabase client
        user_id: User ID to check

    Returns:
        Total number of pages the user has uploaded
    """
    try:
        # Get pages from documents (includes videos)
        doc_response = supabase.table("ragie_documents").select(
            "page_count"
        ).eq("user_id", user_id).execute()

        doc_pages = 0
        if doc_response.data:
            # Sum page_count, treating NULL as 1 page
            doc_pages = sum(doc.get("page_count") or 1 for doc in doc_response.data)

        return doc_pages
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
    Get the number of files uploaded in the current month (permanent record).
    This queries the user_monthly_file_count table which maintains a permanent
    record of uploads and is NOT affected by file deletions.

    Args:
        supabase: Supabase client
        user_id: User ID to check

    Returns:
        Number of files uploaded this month (permanent record)
    """
    try:
        # Get current month in YYYY-MM format
        now = datetime.utcnow()
        current_month = now.strftime("%Y-%m")

        response = supabase.table("user_monthly_file_count").select(
            "total_files_uploaded"
        ).eq("user_id", user_id).eq("month", current_month).execute()

        if response.data and len(response.data) > 0:
            return response.data[0].get("total_files_uploaded", 0)

        return 0
    except Exception as e:
        logger.error(f"Error fetching monthly file count: {e}")
        return 0


def add_to_user_monthly_file_count(supabase, user_id: str) -> bool:
    """
    Increment a user's monthly file upload count by 1. Creates the record if it doesn't exist.
    Automatically resets on the 1st of each month (month is keyed by YYYY-MM).
    This maintains a permanent record that is NOT affected by file deletions.

    Args:
        supabase: Supabase client
        user_id: User ID

    Returns:
        True if successful, False otherwise
    """
    try:
        now = datetime.utcnow()
        current_month = now.strftime("%Y-%m")

        # Try to update existing record
        response = supabase.table("user_monthly_file_count").select(
            "id, total_files_uploaded"
        ).eq("user_id", user_id).eq("month", current_month).execute()

        if response.data and len(response.data) > 0:
            # Update existing record: increment by 1
            record = response.data[0]
            record_id = record["id"]
            current_count = record.get("total_files_uploaded", 0)
            new_total = current_count + 1

            supabase.table("user_monthly_file_count").update({
                "total_files_uploaded": new_total,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", record_id).execute()
        else:
            # Create new record for this month
            supabase.table("user_monthly_file_count").insert({
                "user_id": user_id,
                "month": current_month,
                "total_files_uploaded": 1
            }).execute()

        logger.info(f"Incremented monthly file count for user {user_id} in month {current_month}")
        return True
    except Exception as e:
        logger.error(f"Error adding to user monthly file count: {e}")
        return False


def get_user_max_monthly_throughput(supabase, user_id: str) -> int:
    """
    Get the maximum monthly upload throughput (in bytes) for a user.
    Returns the max_monthly_throughput_bytes from user_settings, or default if not set.

    Args:
        supabase: Supabase client
        user_id: User ID to check

    Returns:
        Maximum bytes allowed per month (5GB for free, 100GB for premium)
    """
    try:
        response = supabase.table("user_settings").select(
            "max_monthly_throughput_bytes, stripe_subscription_status"
        ).eq("user_id", user_id).execute()

        if response.data and len(response.data) > 0:
            settings = response.data[0]
            max_throughput = settings.get("max_monthly_throughput_bytes", DEFAULT_MAX_MONTHLY_THROUGHPUT)

            # Verify subscription status matches throughput limit
            subscription_status = settings.get("stripe_subscription_status")
            if subscription_status in ["active", "trialing"]:
                # Should be premium tier
                if max_throughput < PREMIUM_MAX_MONTHLY_THROUGHPUT:
                    logger.warning(
                        f"User {user_id} has active subscription but max_monthly_throughput_bytes={max_throughput}, "
                        f"expected {PREMIUM_MAX_MONTHLY_THROUGHPUT}"
                    )
                    return PREMIUM_MAX_MONTHLY_THROUGHPUT

            return max_throughput

        # If no settings exist, return default
        return DEFAULT_MAX_MONTHLY_THROUGHPUT
    except Exception as e:
        logger.error(f"Error fetching user monthly throughput limit: {e}")
        return DEFAULT_MAX_MONTHLY_THROUGHPUT


def get_user_monthly_throughput(supabase, user_id: str) -> int:
    """
    Get the current monthly upload throughput (in bytes) for a user in the current month.
    Month is in YYYY-MM format.

    Args:
        supabase: Supabase client
        user_id: User ID to check

    Returns:
        Total bytes uploaded in the current month
    """
    try:
        # Get current month in YYYY-MM format
        now = datetime.utcnow()
        current_month = now.strftime("%Y-%m")

        response = supabase.table("user_monthly_throughput").select(
            "total_bytes_uploaded"
        ).eq("user_id", user_id).eq("month", current_month).execute()

        if response.data and len(response.data) > 0:
            return response.data[0].get("total_bytes_uploaded", 0)

        return 0
    except Exception as e:
        logger.error(f"Error fetching user monthly throughput: {e}")
        return 0


def add_to_user_monthly_throughput(supabase, user_id: str, bytes_uploaded: int) -> bool:
    """
    Add bytes to a user's current month throughput. Creates the record if it doesn't exist.
    Automatically resets on the 1st of each month (month is keyed by YYYY-MM).

    Args:
        supabase: Supabase client
        user_id: User ID
        bytes_uploaded: Number of bytes to add

    Returns:
        True if successful, False otherwise
    """
    try:
        now = datetime.utcnow()
        current_month = now.strftime("%Y-%m")

        # Try to update existing record
        response = supabase.table("user_monthly_throughput").select(
            "id, total_bytes_uploaded"
        ).eq("user_id", user_id).eq("month", current_month).execute()

        if response.data and len(response.data) > 0:
            # Update existing record: fetch current value and add to it
            record = response.data[0]
            record_id = record["id"]
            current_bytes = record.get("total_bytes_uploaded", 0)
            new_total = current_bytes + bytes_uploaded

            supabase.table("user_monthly_throughput").update({
                "total_bytes_uploaded": new_total,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", record_id).execute()
        else:
            # Create new record for this month
            supabase.table("user_monthly_throughput").insert({
                "user_id": user_id,
                "month": current_month,
                "total_bytes_uploaded": bytes_uploaded
            }).execute()

        logger.info(f"Added {bytes_uploaded} bytes to throughput for user {user_id} in month {current_month}")
        return True
    except Exception as e:
        logger.error(f"Error adding to user monthly throughput: {e}")
        return False


def check_user_can_upload(supabase, user_id: str, file_size_bytes: int = 0) -> dict:
    """
    Check if a user can upload a file based on their page, monthly file, and monthly throughput limits.

    Args:
        supabase: Supabase client
        user_id: User ID to check
        file_size_bytes: Size of the file being uploaded (for throughput check)

    Returns:
        Dict with can_upload (bool), current_count (int), max_files (int), remaining (int),
        monthly_count (int), max_monthly (int), and throughput information

    Raises:
        HTTPException: 403 if user has reached any limit
    """
    try:
        # Get settings using consolidated helper (1 query instead of 2)
        settings = _get_user_settings_once(supabase, user_id)
        max_files = settings["max_files"]
        max_monthly = settings["max_monthly_files"]

        # Get current counts
        current_page_count = get_user_file_count(supabase, user_id)
        monthly_file_count = get_user_monthly_file_count(supabase, user_id)
        max_monthly_throughput = get_user_max_monthly_throughput(supabase, user_id)
        current_monthly_throughput = get_user_monthly_throughput(supabase, user_id)

    except Exception as e:
        logger.error(f"Error checking upload capability: {e}")
        # Return default on error to not block uploads
        current_page_count = 0
        monthly_file_count = 0
        current_monthly_throughput = 0
        max_files = DEFAULT_MAX_FILES
        max_monthly = DEFAULT_MAX_MONTHLY_FILES
        max_monthly_throughput = DEFAULT_MAX_MONTHLY_THROUGHPUT

    # Check page quota
    page_can_upload = current_page_count < max_files
    page_remaining = max(0, max_files - current_page_count)
    page_over_limit = max(0, current_page_count - max_files)

    # Check monthly file quota
    monthly_can_upload = monthly_file_count < max_monthly
    monthly_remaining = max(0, max_monthly - monthly_file_count)

    # Check monthly throughput quota
    throughput_can_upload = (current_monthly_throughput + file_size_bytes) <= max_monthly_throughput
    throughput_remaining = max(0, max_monthly_throughput - current_monthly_throughput)

    can_upload = page_can_upload and monthly_can_upload and throughput_can_upload

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
        elif not throughput_can_upload:
            remaining_gb = throughput_remaining / (1024**3)
            file_size_gb = file_size_bytes / (1024**3)
            message = (
                f"You have reached your monthly upload throughput limit of {max_monthly_throughput / (1024**3):.1f} GB. "
                f"You've already uploaded {current_monthly_throughput / (1024**3):.2f} GB this month and this file is {file_size_gb:.2f} GB. "
                f"You have {remaining_gb:.2f} GB remaining. Please try again next month or upgrade to premium."
            )

        raise HTTPException(
            status_code=403,
            detail={
                "error": "file_limit_reached",
                "message": message,
                "current_page_count": current_page_count,
                "max_files": max_files,
                "monthly_file_count": monthly_file_count,
                "max_monthly_files": max_monthly,
                "current_monthly_throughput": current_monthly_throughput,
                "max_monthly_throughput": max_monthly_throughput
            }
        )

    return {
        "can_upload": can_upload,
        "current_page_count": current_page_count,
        "max_files": max_files,
        "page_remaining": page_remaining,
        "monthly_file_count": monthly_file_count,
        "max_monthly_files": max_monthly,
        "monthly_remaining": monthly_remaining,
        "current_monthly_throughput": current_monthly_throughput,
        "max_monthly_throughput": max_monthly_throughput,
        "throughput_remaining": throughput_remaining
    }


def get_user_quota_status(supabase, user_id: str) -> dict:
    """
    Get detailed quota status for a user (pages, monthly files, and monthly throughput).
    Optimized to use minimal queries.

    Args:
        supabase: Supabase client
        user_id: User ID to check

    Returns:
        Dict with quota information
    """
    # Query 1: Get all settings at once
    settings = _get_user_settings_once(supabase, user_id)
    max_files = settings["max_files"]
    max_monthly_files = settings["max_monthly_files"]

    # Query 2: Get current page count (2 sub-queries for documents + videos)
    current_page_count = get_user_file_count(supabase, user_id)

    # Query 3: Get monthly file count (2 sub-queries for documents + videos)
    monthly_file_count = get_user_monthly_file_count(supabase, user_id)

    # Query 4: Get monthly throughput
    max_monthly_throughput = get_user_max_monthly_throughput(supabase, user_id)
    current_monthly_throughput = get_user_monthly_throughput(supabase, user_id)

    # Page quota
    page_remaining = max(0, max_files - current_page_count)
    page_over_limit = max(0, current_page_count - max_files)
    page_is_over_limit = current_page_count > max_files
    page_can_upload = current_page_count < max_files
    page_percentage_used = min(100, int((current_page_count / max_files) * 100)) if max_files > 0 else 0

    # Monthly file quota
    monthly_remaining = max(0, max_monthly_files - monthly_file_count)
    monthly_can_upload = monthly_file_count < max_monthly_files
    monthly_percentage_used = min(100, int((monthly_file_count / max_monthly_files) * 100)) if max_monthly_files > 0 else 0

    # Monthly throughput quota
    throughput_remaining = max(0, max_monthly_throughput - current_monthly_throughput)
    throughput_can_upload = current_monthly_throughput < max_monthly_throughput
    throughput_percentage_used = min(100, int((current_monthly_throughput / max_monthly_throughput) * 100)) if max_monthly_throughput > 0 else 0

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
        # Monthly throughput quota
        "current_monthly_throughput": current_monthly_throughput,
        "max_monthly_throughput": max_monthly_throughput,
        "throughput_remaining": throughput_remaining,
        "throughput_can_upload": throughput_can_upload,
        "throughput_percentage_used": throughput_percentage_used,
        # Overall
        "can_upload": page_can_upload and monthly_can_upload and throughput_can_upload
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
