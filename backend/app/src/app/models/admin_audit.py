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


class AdminActionTargetType(str, enum.Enum):
    Inventory = "inventory"
    Order = "order"
    Store = "store"
    SellerProfile = "seller_profile"


class AdminActionLog(SQLModel, table=True):
    __tablename__ = "admin_action_log"
    __table_args__ = (
        Index(
            "ix_admin_action_log_seller_created",
            "target_seller_id",
            "created_at",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        nullable=False,
    )
    admin_user_id: int = Field(
        foreign_key="user.id", nullable=False, index=True
    )
    target_seller_id: int = Field(
        foreign_key="sellerprofile.id", nullable=False
    )
    target_type: AdminActionTargetType = Field(nullable=False)
    target_id: int = Field(nullable=False)
    action: str = Field(max_length=64, nullable=False)
    before_json: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    after_json: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    reason: Optional[str] = Field(default=None, max_length=500)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
