# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Courier-order data (spec 2026-10-02 §6.3).

`CourierQuote` is append-only: every send or revise inserts a version, so the
record shows exactly what the customer was offered. `OrderCourier` holds the
per-order courier state that has no home on Order/Delivery/Payment.
"""
from datetime import date, datetime
from typing import Optional

from sqlmodel import DateTime, Field, UniqueConstraint

from app.models.base import BaseSchema


class CourierQuote(BaseSchema, table=True):
    __tablename__ = "courier_quote"
    __table_args__ = (
        UniqueConstraint("order_id", "version", name="uq_courier_quote_order_version"),
    )
    order_id: int = Field(foreign_key="order.id", nullable=False, index=True)
    version: int = Field(nullable=False)
    courier_fee: float = Field(nullable=False)
    # Transit counted from payment confirmation, not calendar dates (spec D8).
    eta_min_days: int = Field(nullable=False)
    eta_max_days: int = Field(nullable=False)
    carrier_name: Optional[str] = Field(default=None, max_length=80)
    note: Optional[str] = Field(default=None, max_length=300)
    created_by_user_id: int = Field(foreign_key="user.id", nullable=False)


class OrderCourier(BaseSchema, table=True):
    __tablename__ = "order_courier"
    order_id: int = Field(foreign_key="order.id", nullable=False, unique=True, index=True)
    recipient_name: str = Field(nullable=False, max_length=120)
    recipient_phone: str = Field(nullable=False, max_length=20)
    # The checkout opt-in, so acceptance can top store credit up (spec D16).
    apply_store_credit: bool = Field(default=True, nullable=False)
    accepted_quote_id: Optional[int] = Field(default=None, foreign_key="courier_quote.id")
    accepted_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )
    # Fixed when payment is confirmed: IST date + quoted min/max days.
    eta_from: Optional[date] = Field(default=None)
    eta_to: Optional[date] = Field(default=None)
    payment_claim_rejected_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )
    payment_claim_rejected_note: Optional[str] = Field(default=None, max_length=300)
    # Keys the payment reminders (spec §11.2) so a rejection starts a new stage.
    payment_claim_rejection_count: int = Field(default=0, nullable=False)
    carrier_name: Optional[str] = Field(default=None, max_length=80)
    tracking_number: Optional[str] = Field(default=None, max_length=60)
    tracking_url: Optional[str] = Field(default=None, max_length=500)
    tracking_updated_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )
    # "seller" | "customer" | "admin" — a string, like ReturnEvent.actor_role.
    delivered_by: Optional[str] = Field(default=None, max_length=16)
    cancel_reason: Optional[str] = Field(default=None, max_length=300)
    cancelled_by: Optional[str] = Field(default=None, max_length=16)
    cancelled_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )
    # Set when a cancel answers "No, the money didn't arrive" to a claim.
    payment_reported_missing_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )
    last_reminder_key: Optional[str] = Field(default=None, max_length=40)
    last_reminder_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )
