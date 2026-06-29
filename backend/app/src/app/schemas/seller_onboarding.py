# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.models.seller_onboarding_request import OnboardingRequestStatus


class SellerOnboardingRequestCreate(BaseModel):
    store_name: str = Field(min_length=1, max_length=120)
    contact_phone: str = Field(min_length=8, max_length=20)
    contact_email: EmailStr
    contact_address: str = Field(min_length=1, max_length=500)
    preferred_categories: Optional[str] = Field(default=None, max_length=300)
    area_lat: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    area_lng: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    area_label: Optional[str] = Field(default=None, max_length=120)
    source: Optional[str] = Field(default=None, max_length=16)


class SellerOnboardingRequestRead(BaseModel):
    id: int
    store_name: str
    contact_phone: str
    contact_email: str
    contact_address: str
    preferred_categories: Optional[str]
    area_lat: Optional[float]
    area_lng: Optional[float]
    area_label: Optional[str]
    source: Optional[str]
    submitted_by_user_id: Optional[int]
    status: OnboardingRequestStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SellerOnboardingRequestStatusUpdate(BaseModel):
    status: OnboardingRequestStatus
