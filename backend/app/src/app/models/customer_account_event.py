# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

from app.models.base import AccountStatus


class CustomerAccountEvent(SQLModel, table=True):
    # Explicit — SQLModel would otherwise name this "customeraccountevent"
    # (lowercased class name with NO underscores).
    __tablename__ = "customer_account_event"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", nullable=False, index=True)
    actor_user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    actor_role: str = Field(max_length=16, nullable=False)
    from_status: AccountStatus = Field(nullable=False)
    to_status: AccountStatus = Field(nullable=False)
    reason: Optional[str] = Field(default=None, max_length=500)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
