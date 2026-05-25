# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import enum
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import DateTime, Field, Index

from app.models.base import BaseSchema


class NotificationType(str, enum.Enum):
    OrderStatus = "order_status"


class Notification(BaseSchema, table=True):
    __table_args__ = (
        Index("ix_notification_customer_created", "customer_profile_id", "created_at"),
    )
    customer_profile_id: int = Field(
        foreign_key="customerprofile.id", nullable=False, index=True
    )
    order_id: Optional[int] = Field(default=None, foreign_key="order.id")
    type: NotificationType = Field(default=NotificationType.OrderStatus, nullable=False)
    title: str = Field(nullable=False)
    body: str = Field(nullable=False)
    status_value: str = Field(nullable=False)
    read: bool = Field(default=False, nullable=False)


class PushSubscription(BaseSchema, table=True):
    __tablename__ = "pushsubscription"
    customer_profile_id: int = Field(
        foreign_key="customerprofile.id", nullable=False, index=True
    )
    endpoint: str = Field(nullable=False, unique=True, index=True)
    p256dh: str = Field(nullable=False)
    auth: str = Field(nullable=False)
    user_agent: Optional[str] = Field(default=None)
    last_seen_at: datetime = Field(  # type: ignore[call-overload]
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )
