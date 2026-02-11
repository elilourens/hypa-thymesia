"""Document group management endpoints."""

import logging
from fastapi import APIRouter, Depends, HTTPException

from supabase import Client
from core import get_current_user, AuthUser
from core.deps import get_supabase
from schemas import GroupCreate, GroupResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("", response_model=list[GroupResponse])
async def list_groups(
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """List all document groups for the user."""
    try:
        response = supabase.table("app_groups").select(
            "*"
        ).eq("user_id", current_user.id).order("sort_index").execute()

        return [
            GroupResponse(
                id=group["group_id"],
                name=group["name"],
                created_at=group["created_at"],
                sort_index=group.get("sort_index"),
                color=group.get("color", "#8B5CF6"),
            )
            for group in (response.data or [])
        ]

    except Exception as e:
        logger.error(f"Error listing groups: {e}")
        raise HTTPException(status_code=500, detail="Failed to list groups")


@router.post("", response_model=GroupResponse)
async def create_group(
    request: GroupCreate,
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Create a new document group."""
    try:
        response = supabase.table("app_groups").insert({
            "user_id": current_user.id,
            "name": request.name,
            "sort_index": request.sort_index or 0,
            "color": request.color or "#8B5CF6"
        }).execute()

        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create group")

        group = response.data[0]
        return GroupResponse(
            id=group["group_id"],
            name=group["name"],
            created_at=group["created_at"],
            sort_index=group.get("sort_index"),
            color=group.get("color", "#8B5CF6"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating group: {e}")
        raise HTTPException(status_code=500, detail="Failed to create group")


@router.patch("/{group_id}", response_model=GroupResponse)
async def rename_group(
    group_id: str,
    request: GroupCreate,
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Rename/update a group."""
    try:
        # Check group exists
        get_response = supabase.table("app_groups").select(
            "*"
        ).eq("group_id", group_id).eq("user_id", current_user.id).single().execute()

        if not get_response.data:
            raise HTTPException(status_code=404, detail="Group not found")

        # Update group
        update_data = {"name": request.name}
        if request.sort_index is not None:
            update_data["sort_index"] = request.sort_index
        if hasattr(request, 'color') and request.color is not None:
            update_data["color"] = request.color

        response = supabase.table("app_groups").update(
            update_data
        ).eq("group_id", group_id).execute()

        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to update group")

        group = response.data[0]
        return GroupResponse(
            id=group["group_id"],
            name=group["name"],
            created_at=group["created_at"],
            sort_index=group.get("sort_index"),
            color=group.get("color", "#8B5CF6"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating group: {e}")
        raise HTTPException(status_code=500, detail="Failed to update group")


@router.delete("/{group_id}")
async def delete_group(
    group_id: str,
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Delete a group."""
    try:
        # Check group exists
        get_response = supabase.table("app_groups").select(
            "*"
        ).eq("group_id", group_id).eq("user_id", current_user.id).single().execute()

        if not get_response.data:
            raise HTTPException(status_code=404, detail="Group not found")

        # Delete group
        supabase.table("app_groups").delete().eq("group_id", group_id).execute()

        return {"message": "Group deleted successfully", "group_id": group_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting group: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete group")
