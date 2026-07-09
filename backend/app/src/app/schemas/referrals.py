# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.core.indian_states import INDIAN_STATES
from app.core.otp import InvalidPhoneNumber, normalize_phone
from app.models.base import UserRole
from app.models.referral import ReferralStatus, ReferralTargetRole


class ReferralCreate(BaseModel):
    target_role: ReferralTargetRole
    invitee_name: str = Field(min_length=1, max_length=120)
    invitee_phone: Optional[str] = Field(default=None, max_length=20)
    invitee_email: Optional[EmailStr] = None
    location_state: str = Field(min_length=1, max_length=80)
    location_area: str = Field(min_length=1, max_length=160)

    @model_validator(mode="after")
    def _validate(self) -> "ReferralCreate":
        if not self.invitee_phone and not self.invitee_email:
            raise ValueError("at least one of invitee_phone / invitee_email is required")
        if self.location_state not in INDIAN_STATES:
            raise ValueError("location_state must be a valid Indian state/UT")
        if self.invitee_email:
            self.invitee_email = self.invitee_email.lower()
        if self.invitee_phone:
            try:
                self.invitee_phone = normalize_phone(self.invitee_phone)
            except InvalidPhoneNumber as exc:
                raise ValueError("invitee_phone must be a valid +91 mobile number") from exc
        return self


class ReferralRead(BaseModel):
    id: int
    source_user_id: int
    source_role: UserRole
    target_role: ReferralTargetRole
    invitee_name: str
    invitee_phone: Optional[str]
    invitee_email: Optional[str]
    location_state: str
    location_area: str
    status: ReferralStatus
    rejection_reason: Optional[str]
    activated_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ReferralInviteDetail(BaseModel):
    """Public landing-page view of an invite, derived from the token + row."""

    invitee_name: str
    target_role: ReferralTargetRole
    invitee_email: Optional[str]
    invitee_phone: Optional[str]
    expired: bool
    status: ReferralStatus


class ReferralAcceptBody(BaseModel):
    """Customer-target activation: verify OTP for the invitee email + create
    the account. ``email`` is only needed for phone-only invites (the token
    carries no email); otherwise the token's email is authoritative."""

    token: str
    code: str = Field(min_length=4, max_length=8)
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(default=None, max_length=120)
    accept_policies: bool = False


class AdminReferralReject(BaseModel):
    reason: str = Field(min_length=1, max_length=300)


class ReferralSettingsRead(BaseModel):
    require_admin_approval: bool
    model_config = {"from_attributes": True}


class ReferralSettingsPatch(BaseModel):
    require_admin_approval: bool
