# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import CheckConstraint
from sqlmodel import DateTime, Field, Index

from app.models.base import BaseSchema


class NotificationType(str, enum.Enum):
    OrderStatus = "order_status"
    DeliveryOtp = "delivery_otp"
    FeeActivated = "fee_activated"
    FeeExpiring = "fee_expiring"
    FeeSuspended = "fee_suspended"
    FeeLowBalance = "fee_low_balance"
    FeeReactivated = "fee_reactivated"
    FeeInvoiceRaised = "fee_invoice_raised"
    FeeInvoiceOverdue = "fee_invoice_overdue"
    Referral = "referral"
    Credit = "credit"
    Announcement = "announcement"


class Notification(BaseSchema, table=True):
    __table_args__ = (
        Index("ix_notification_customer_created", "customer_profile_id", "created_at"),
        Index("ix_notification_seller_created", "seller_profile_id", "created_at"),
        CheckConstraint(
            "(customer_profile_id IS NOT NULL) <> (seller_profile_id IS NOT NULL)",
            name="ck_notification_one_recipient",
        ),
    )
    customer_profile_id: Optional[int] = Field(
        default=None, foreign_key="customerprofile.id", nullable=True, index=True
    )
    seller_profile_id: Optional[int] = Field(
        default=None, foreign_key="sellerprofile.id", nullable=True, index=True
    )
    order_id: Optional[int] = Field(default=None, foreign_key="order.id")
    campaign_id: Optional[int] = Field(
        default=None, foreign_key="notification_campaign.id", nullable=True
    )
    type: NotificationType = Field(default=NotificationType.OrderStatus, nullable=False)
    title: str = Field(nullable=False)
    body: str = Field(nullable=False)
    status_value: str = Field(nullable=False)
    read: bool = Field(default=False, nullable=False)
    image_url: Optional[str] = Field(default=None, max_length=500)
    cta_url: Optional[str] = Field(default=None, max_length=500)
    cta_label: Optional[str] = Field(default=None, max_length=80)


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
