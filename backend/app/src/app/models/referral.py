# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index
from sqlmodel import Field

from app.models.base import BaseSchema, UserRole


class ReferralStatus(str, enum.Enum):
    # Lowercase names == values so the native PG enum created by metadata
    # matches the hand-written migration.
    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"
    active = "active"
    expired = "expired"


class ReferralTargetRole(str, enum.Enum):
    customer = "customer"
    seller = "seller"


class Referral(BaseSchema, table=True):
    """A user-initiated referral to onboard a new customer or seller.

    FK-less ``source_user_id`` / ``activated_user_id`` / ``reviewed_by_admin_id``
    so referral history survives user deletion (mirrors seller_onboarding_request).
    The row itself is the audit record: who initiated, who reviewed and when,
    the rejection reason, and the activation outcome.
    """

    __tablename__ = "referral"
    __table_args__ = (
        Index("ix_referral_source_status", "source_user_id", "status"),
        Index("ix_referral_status", "status"),
    )

    source_user_id: int = Field(nullable=False, index=True)
    source_role: UserRole = Field(nullable=False)
    target_role: ReferralTargetRole = Field(nullable=False)
    invitee_name: str = Field(nullable=False, max_length=120)
    invitee_phone: Optional[str] = Field(default=None, max_length=20)
    invitee_email: Optional[str] = Field(default=None, max_length=254)
    location_state: str = Field(nullable=False, max_length=80)
    location_area: str = Field(nullable=False, max_length=160)
    status: ReferralStatus = Field(default=ReferralStatus.pending_review, nullable=False)
    rejection_reason: Optional[str] = Field(default=None, max_length=300)
    reviewed_by_admin_id: Optional[int] = Field(default=None)
    reviewed_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )
    invite_expires_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )
    activated_user_id: Optional[int] = Field(default=None)
    activated_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )


class ReferralSettings(BaseSchema, table=True):
    """Single-row global config for the referral subsystem (mirrors
    PlatformFeeSettings). ``require_admin_approval`` is the spec's
    'optional, configurable' approval gate."""

    __tablename__ = "referral_settings"

    require_admin_approval: bool = Field(default=True, nullable=False)
