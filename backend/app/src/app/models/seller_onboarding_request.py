# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import enum
from typing import Optional

from sqlmodel import Field

from app.models.base import BaseSchema


class OnboardingRequestStatus(str, enum.Enum):
    # Lowercase names == values so the native PG enum created by metadata
    # matches the hand-written migration.
    new = "new"
    contacted = "contacted"
    onboarded = "onboarded"
    dismissed = "dismissed"


class SellerOnboardingRequest(BaseSchema, table=True):
    """A visitor-submitted lead: a seller/store they want onboarded, captured
    from the deliverability fallback. Reviewed by admins; no FK on
    submitted_by_user_id so lead history survives user deletion."""

    __tablename__ = "seller_onboarding_request"

    store_name: str = Field(nullable=False, max_length=120)
    contact_phone: str = Field(nullable=False, max_length=20)
    contact_email: str = Field(nullable=False, max_length=254)
    contact_address: str = Field(nullable=False, max_length=500)
    preferred_categories: Optional[str] = Field(default=None, max_length=300)
    area_lat: Optional[float] = Field(default=None)
    area_lng: Optional[float] = Field(default=None)
    area_label: Optional[str] = Field(default=None, max_length=120)
    source: Optional[str] = Field(default=None, max_length=16)
    submitted_by_user_id: Optional[int] = Field(default=None, index=True)
    status: OnboardingRequestStatus = Field(
        default=OnboardingRequestStatus.new, nullable=False
    )
