"""User-related Pydantic schemas."""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class UserSettings(BaseModel):
    """User settings."""

    user_id: str
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    stripe_subscription_status: Optional[str] = None
    stripe_current_period_end: Optional[int] = None
    stripe_cancel_at_period_end: Optional[bool] = False
    max_files: int = 50
    created_at: datetime
    updated_at: datetime


class UserQuotaStatus(BaseModel):
    """User quota status."""

    current_count: int
    max_files: int
    remaining: int
    over_limit: int
    is_over_limit: bool
    can_upload: bool
    percentage_used: int


class GroupCreate(BaseModel):
    """Create group request."""

    name: str = Field(..., max_length=30)
    sort_index: Optional[int] = None
    color: str = '#8B5CF6'


class GroupResponse(BaseModel):
    """Group response."""

    id: str
    name: str = Field(..., max_length=30)
    created_at: datetime
    sort_index: Optional[int] = None
    color: str
