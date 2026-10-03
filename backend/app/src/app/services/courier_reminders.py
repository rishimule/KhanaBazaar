# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Hourly courier reminders (spec 2026-10-02 §11.2). Never changes order state.

One reminder per stage key; a revised quote or a rejected payment claim starts
a new key, and refund keys only move forward. Each order is locked (skipping
rows a live request holds), re-checked, stamped and committed BEFORE its
messages are queued, so a crash can lose a reminder but never doubles one.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, or_
from sqlmodel import col, select

from app.core.config import settings
from app.db import session as db_session
from app.models.commerce import DeliveryMode, Order, OrderStatus, Payment, PaymentStatus
from app.models.courier import CourierQuote, OrderCourier
from app.services.courier import store_seller
from app.services.courier_comms import notify_customer, notify_seller
from app.services.courier_rules import refund_owed, refund_owed_order_ids
from app.services.serviceability import courier_payment_methods
from app.utils.delivery_window import IST

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DueReminder:
    key: str
    customer_event: str | None = None
    seller_event: str | None = None


def due_reminder(
    *,
    status: OrderStatus,
    payment_status: PaymentStatus,
    payment_amount: float,
    placed_at: datetime,
    latest_quote_version: int | None,
    latest_quote_at: datetime | None,
    accepted_at: datetime | None,
    claimed_at: datetime | None,
    rejected_at: datetime | None,
    rejection_count: int,
    eta_to: date | None,
    cancelled_at: datetime | None,
    now: datetime,
) -> DueReminder | None:
    """Which reminder (if any) is due for an order in this state, right now."""
    wait = timedelta(hours=settings.COURIER_REMINDER_HOURS)
    if status is OrderStatus.Pending:
        return DueReminder("pending", seller_event="reminder_quote") if now - placed_at >= wait else None
    if status is OrderStatus.Quoted:
        if latest_quote_at is None or latest_quote_version is None or now - latest_quote_at < wait:
            return None
        return DueReminder(f"quoted:v{latest_quote_version}", customer_event="reminder_quote")
    if status is OrderStatus.Accepted:
        if claimed_at is None:
            moved = [t for t in (accepted_at, rejected_at) if t is not None]
            if not moved or now - max(moved) < wait:
                return None
            return DueReminder(f"accepted:r{rejection_count}", customer_event="reminder_payment")
        if now - claimed_at < wait:
            return None
        return DueReminder(f"claimed:r{rejection_count}", seller_event="reminder_payment_check")
    if status is OrderStatus.Dispatched:
        today = now.astimezone(IST).date()
        if eta_to is None or today <= eta_to + timedelta(days=settings.COURIER_ARRIVAL_GRACE_DAYS):
            return None
        return DueReminder(
            "overdue", customer_event="reminder_arrival", seller_event="reminder_overdue"
        )
    if refund_owed(status, payment_status, payment_amount) and cancelled_at is not None:
        age = now - cancelled_at
        reached = [d for d in settings.COURIER_REFUND_REMINDER_DAYS if age >= timedelta(days=d)]
        if reached:
            return DueReminder(f"refund:{reached[-1]}", seller_event="reminder_refund")
    return None


def in_send_window(now: datetime) -> bool:
    """False during the quiet hours [QUIET_START, QUIET_END), IST.

    The quiet window may wrap past midnight (21 → 9, the default) or not
    (0 → 7); START == END means there are no quiet hours at all.
    """
    hour = now.astimezone(IST).hour
    start, end = settings.COURIER_QUIET_START_HOUR, settings.COURIER_QUIET_END_HOUR
    if start == end:
        return True
    if start > end:
        return end <= hour < start
    return not start <= hour < end


async def _candidate_ids() -> list[int]:
    async with db_session.async_session_factory() as session:
        refund_due = refund_owed_order_ids()
        rows = await session.exec(
            select(Order.id)
            .where(
                Order.delivery_mode == DeliveryMode.Courier,
                or_(
                    col(Order.status).in_(
                        [OrderStatus.Pending, OrderStatus.Quoted, OrderStatus.Accepted, OrderStatus.Dispatched]
                    ),
                    and_(col(Order.status) == OrderStatus.Cancelled, col(Order.id).in_(refund_due)),
                ),
            )
            .order_by(col(Order.id))
        )
        return [int(i) for i in rows.all() if i is not None]


async def _remind_one(order_id: int, now: datetime) -> bool:
    async with db_session.async_session_factory() as session:
        order = (
            await session.exec(
                select(Order).where(Order.id == order_id).with_for_update(skip_locked=True)
            )
        ).first()
        if order is None:
            return False  # a live request holds it; the next sweep will look again
        row = (await session.exec(select(OrderCourier).where(OrderCourier.order_id == order_id))).first()
        payment = (await session.exec(select(Payment).where(Payment.order_id == order_id))).first()
        if row is None or payment is None:
            return False
        quote = (
            await session.exec(
                select(CourierQuote)
                .where(CourierQuote.order_id == order_id)
                .order_by(col(CourierQuote.version).desc())
            )
        ).first()
        due = due_reminder(
            status=order.status,
            payment_status=payment.status,
            payment_amount=payment.amount,
            placed_at=order.placed_at,
            latest_quote_version=quote.version if quote else None,
            latest_quote_at=quote.created_at if quote else None,
            accepted_at=row.accepted_at,
            claimed_at=payment.customer_claimed_at,
            rejected_at=row.payment_claim_rejected_at,
            rejection_count=row.payment_claim_rejection_count,
            eta_to=row.eta_to,
            cancelled_at=row.cancelled_at,
            now=now,
        )
        if due is None or due.key == row.last_reminder_key:
            return False
        if due.customer_event == "reminder_payment" and not courier_payment_methods(
            await store_seller(session, order.store_id)
        ):
            # Telling the customer to pay when they can't would only confuse
            # them; left unstamped, it goes out once a payee is back.
            return False
        row.last_reminder_key = due.key
        row.last_reminder_at = now
        session.add(row)
        await session.commit()
        if due.customer_event:
            await notify_customer(session, order, due.customer_event)
        if due.seller_event:
            await notify_seller(session, order, due.seller_event)
        return True


async def run_courier_reminder_sweep(*, now: datetime | None = None) -> int:
    """Send every due reminder. Returns how many orders were reminded; raises
    after the loop if any order failed, so the worker log shows it."""
    now = now or datetime.now(timezone.utc)
    if not in_send_window(now):
        return 0
    sent = 0
    failures = 0
    for order_id in await _candidate_ids():
        try:
            if await _remind_one(order_id, now):
                sent += 1
        except Exception:
            failures += 1
            logger.exception("Courier reminder failed for order_id=%s", order_id)
    if failures:
        raise RuntimeError(f"{failures} courier reminder(s) failed; {sent} sent")
    return sent
