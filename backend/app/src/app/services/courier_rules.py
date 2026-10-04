# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Pure courier rules + the order row lock (spec 2026-10-02 §9).

No imports from services.orders, so both services.orders and services.courier
can depend on this module without a cycle.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from app.models.commerce import (
    DeliveryStatus,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
)
from app.models.courier import OrderCourier

S = OrderStatus

COURIER_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    S.Pending: frozenset({S.Quoted, S.Cancelled}),
    S.Quoted: frozenset({S.Quoted, S.Accepted, S.Cancelled}),
    S.Accepted: frozenset({S.Paid, S.Cancelled}),
    S.Paid: frozenset({S.Packed, S.Cancelled}),
    S.Packed: frozenset({S.Dispatched, S.Cancelled}),
    S.Dispatched: frozenset({S.Delivered, S.Cancelled}),
    S.Delivered: frozenset(),
    S.Cancelled: frozenset(),
}

# Admin-only backward moves. Never back before acceptance: the customer's
# consent to the price is not something an admin can undo (spec §9.7).
COURIER_REWIND_TARGETS: dict[OrderStatus, frozenset[OrderStatus]] = {
    S.Paid: frozenset({S.Accepted}),
    S.Packed: frozenset({S.Paid}),
    S.Dispatched: frozenset({S.Paid, S.Packed}),
}

_PRE_FULFILMENT = frozenset({S.Pending, S.Quoted, S.Accepted, S.Paid})


def delivery_status_for(status: OrderStatus) -> DeliveryStatus:
    """Delivery only tracks fulfilment; everything before packing is pending."""
    if status in _PRE_FULFILMENT:
        return DeliveryStatus.Pending
    return DeliveryStatus(status.value)


def refund_owed(status: OrderStatus, payment_status: PaymentStatus, amount: float) -> bool:
    """Cancelled with the customer's money still with the seller (spec §10.3).

    A ₹0 payment — store credit covered everything, and that credit comes back
    on its own at cancel (revert_order) — owes nothing: no "refund due" badge,
    no "Refunds due" listing, no refund reminders, no "Refund sent" to tap.
    """
    return status == S.Cancelled and payment_status == PaymentStatus.Paid and amount > 0


def refund_owed_order_ids() -> SelectOfScalar[int]:
    """SQL twin of refund_owed's payment half: order ids whose payment is Paid
    and non-zero. Callers add the Cancelled (+ courier) conditions on Order."""
    return select(Payment.order_id).where(
        Payment.status == PaymentStatus.Paid, col(Payment.amount) > 0
    )


def eta_window(min_days: int, max_days: int, *, today: date) -> tuple[date, date]:
    return today + timedelta(days=min_days), today + timedelta(days=max_days)


def clean_text(value: str | None, *, max_len: int) -> str | None:
    """Strip; empty → None; clamp to `max_len`."""
    if value is None:
        return None
    return value.strip()[:max_len] or None


def validate_tracking_url(url: str | None) -> str | None:
    """https only, a host, no embedded credentials, at most 500 characters.
    Raises ValueError("invalid_tracking_url"); "" or None → None (clear)."""
    if url is None or not url.strip():
        return None
    cleaned = url.strip()
    parts = urlsplit(cleaned)
    if (
        len(cleaned) > 500
        or parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
    ):
        raise ValueError("invalid_tracking_url")
    return cleaned


@dataclass(frozen=True)
class TrackingInput:
    """Per field: None = leave alone, "" = clear, anything else = set."""

    carrier_name: str | None = None
    tracking_number: str | None = None
    tracking_url: str | None = None

    def any(self) -> bool:
        return any(
            v is not None for v in (self.carrier_name, self.tracking_number, self.tracking_url)
        )


def apply_tracking(row: OrderCourier, tracking: TrackingInput) -> bool:
    """Write the provided tracking fields onto `row`. Returns whether anything
    changed. Call validate_tracking_url first — this re-raises its ValueError."""
    changed = False
    for attr, value, max_len in (
        ("carrier_name", tracking.carrier_name, 80),
        ("tracking_number", tracking.tracking_number, 60),
    ):
        if value is None:
            continue
        new = clean_text(value, max_len=max_len)
        if getattr(row, attr) != new:
            setattr(row, attr, new)
            changed = True
    if tracking.tracking_url is not None:
        new_url = validate_tracking_url(tracking.tracking_url)
        if row.tracking_url != new_url:
            row.tracking_url = new_url
            changed = True
    return changed


async def lock_order(session: AsyncSession, order_id: int) -> Order:
    """Re-read the order under SELECT … FOR UPDATE, refreshing the instance the
    caller holds, so concurrent courier actions serialise (spec §9.8)."""
    order = (
        await session.exec(
            select(Order)
            .where(Order.id == order_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
