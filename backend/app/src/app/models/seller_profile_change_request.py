# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class SellerProfileChangeGroup(str, enum.Enum):
    Identity = "identity"
    Address = "address"
    Legal = "legal"
    Banking = "banking"
    Services = "services"
    StoreBasics = "store_basics"


class SellerProfileChangeStatus(str, enum.Enum):
    Submitted = "submitted"
    ChangesRequested = "changes_requested"
    Approved = "approved"
    Rejected = "rejected"
    Withdrawn = "withdrawn"


class SellerProfileChangeEventKind(str, enum.Enum):
    Submitted = "submitted"
    Resubmitted = "resubmitted"
    ChangesRequested = "changes_requested"
    Approved = "approved"
    ApprovedWithEdits = "approved_with_edits"
    Rejected = "rejected"
    Withdrawn = "withdrawn"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SellerProfileChangeRequest(SQLModel, table=True):
    __tablename__ = "seller_profile_change_request"
    __table_args__ = (
        Index(
            "ix_seller_profile_cr_seller_created",
            "seller_profile_id",
            "created_at",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, nullable=False
    )
    seller_profile_id: int = Field(
        foreign_key="sellerprofile.id", nullable=False, index=True
    )
    group: SellerProfileChangeGroup = Field(nullable=False)
    status: SellerProfileChangeStatus = Field(nullable=False)
    proposed_json: dict[str, Any] = Field(
        sa_column=Column(JSONB, nullable=False)
    )
    applied_json: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    baseline_json: dict[str, Any] = Field(
        sa_column=Column(JSONB, nullable=False)
    )
    admin_note: Optional[str] = Field(default=None)
    submission_count: int = Field(default=1, nullable=False)
    created_at: datetime = Field(
        default_factory=_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    decided_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    decided_by_user_id: Optional[int] = Field(
        default=None, foreign_key="user.id"
    )


class SellerProfileChangeRequestEvent(SQLModel, table=True):
    __tablename__ = "seller_profile_change_request_event"
    __table_args__ = (
        Index(
            "ix_seller_profile_cr_event_cr_created",
            "change_request_id",
            "created_at",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, nullable=False
    )
    change_request_id: uuid.UUID = Field(
        foreign_key="seller_profile_change_request.id",
        nullable=False,
        index=True,
    )
    kind: SellerProfileChangeEventKind = Field(nullable=False)
    actor_user_id: int = Field(foreign_key="user.id", nullable=False)
    # actor_role is a snapshot at event time — UserRole serialized as str
    actor_role: str = Field(max_length=16, nullable=False)
    payload_json: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    note: Optional[str] = Field(default=None)
    created_at: datetime = Field(
        default_factory=_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
