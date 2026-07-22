# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Order Value % (postpaid + security deposit) fee model.

Monthly postpaid billing: on the configured billing day, a FeeInvoice is raised
for the prior calendar month's completed (delivered) sales, charged at the
service's `order_value_percent`. Non-payment (after the payment window + grace)
suspends the arrangement; paying + admin-confirm auto-reactivates. A held
security deposit is collateral, forfeited/refunded only by explicit admin action.

Cycle boundaries are computed in IST (Asia/Kolkata); `Order.placed_at` is
timezone-aware UTC, so period bounds are converted to UTC for the sales query.

Service functions FLUSH; the caller COMMITS (mirrors fee_lifecycle)."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func as safunc
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Order, OrderStatus
from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeEvent,
    FeeEventType,
    FeeInvoice,
    FeeModel,
    InvoiceStatus,
    PlatformFeeSettings,
    ServiceFeeConfig,
)

IST = ZoneInfo("Asia/Kolkata")
DEFAULT_GRACE_DAYS = 2


def _last_day_of_month(d: date) -> int:
    """Last calendar day of the month containing `d`."""
    nxt = d.replace(day=28) + timedelta(days=4)
    return (nxt.replace(day=1) - timedelta(days=1)).day


async def compute_order_value_sales(
    session: AsyncSession,
    store_id: int,
    service_id: int,
    period_start: date,
    period_end: date,
) -> float:
    """Sum the grand total (`Order.total`) of DELIVERED orders for a
    (store, service) whose `placed_at` falls within [period_start, period_end]
    (inclusive), interpreting the date bounds in IST."""
    start_utc = datetime.combine(period_start, time.min, tzinfo=IST)
    end_utc = datetime.combine(period_end + timedelta(days=1), time.min, tzinfo=IST)
    total = (
        await session.exec(
            select(safunc.coalesce(safunc.sum(Order.total), 0.0)).where(
                Order.store_id == store_id,
                Order.service_id == service_id,
                Order.status == OrderStatus.Delivered,
                Order.placed_at >= start_utc,
                Order.placed_at < end_utc,
            )
        )
    ).one()
    return float(total or 0.0)


async def _grace_days(session: AsyncSession) -> int:
    settings = (
        await session.exec(
            select(PlatformFeeSettings).order_by(PlatformFeeSettings.id).limit(1)  # type: ignore[arg-type]
        )
    ).first()
    return settings.grace_period_days if settings else DEFAULT_GRACE_DAYS


async def generate_order_value_invoices(
    session: AsyncSession,
    today: date,
    *,
    notices: list[tuple[int, str, "date | None"]] | None = None,
) -> int:
    """On each arrangement's billing day, raise a FeeInvoice for the prior
    calendar month's completed sales. Idempotent (unique arrangement+period).
    A zero-amount invoice is auto-settled (Paid). Flushes; caller commits.
    Returns the number of invoices created."""
    prev_end = today.replace(day=1) - timedelta(days=1)
    prev_start = prev_end.replace(day=1)
    grace = await _grace_days(session)
    created = 0

    arrangements = (
        await session.exec(
            select(FeeArrangement).where(
                FeeArrangement.model == FeeModel.OrderValuePercent,
                FeeArrangement.status.in_(  # type: ignore[attr-defined]
                    [ArrangementStatus.Active, ArrangementStatus.Grace]
                ),
            )
        )
    ).all()

    for arr in arrangements:
        cfg = (
            await session.exec(
                select(ServiceFeeConfig).where(
                    ServiceFeeConfig.service_id == arr.service_id
                )
            )
        ).first()
        if cfg is None:
            continue
        billing_day = min(cfg.order_value_billing_day, _last_day_of_month(today))
        if today.day != billing_day:
            continue

        period_start = prev_start
        if arr.order_value_activated_on and arr.order_value_activated_on > period_start:
            period_start = arr.order_value_activated_on
        if arr.last_billed_period_end and arr.last_billed_period_end >= period_start:
            period_start = arr.last_billed_period_end + timedelta(days=1)
        if period_start > prev_end:
            continue  # activated after the period closed; bill next cycle

        already = (
            await session.exec(
                select(FeeInvoice).where(
                    FeeInvoice.arrangement_id == arr.id,
                    FeeInvoice.period_start == period_start,
                )
            )
        ).first()
        if already is not None:
            continue

        sales = await compute_order_value_sales(
            session, arr.store_id, arr.service_id, period_start, prev_end
        )
        pct = cfg.order_value_percent
        amount = round(sales * pct / 100.0, 2)
        due = today + timedelta(days=cfg.order_value_payment_days)
        is_zero = amount <= 0.0

        invoice = FeeInvoice(
            arrangement_id=arr.id,
            store_id=arr.store_id,
            service_id=arr.service_id,
            period_start=period_start,
            period_end=prev_end,
            sales_total=sales,
            fee_percent_snapshot=pct,
            amount_due=amount,
            status=InvoiceStatus.Paid if is_zero else InvoiceStatus.Pending,
            issued_on=today,
            due_date=due,
            suspend_after=due + timedelta(days=grace),
            paid_at=datetime.now(timezone.utc) if is_zero else None,
        )
        session.add(invoice)
        if not is_zero:
            arr.balance += amount
        arr.last_billed_period_end = prev_end
        session.add(arr)
        session.add(
            FeeEvent(
                arrangement_id=arr.id,
                event_type=FeeEventType.InvoiceIssued,
                amount_delta=amount,
                actor="system",
                note=f"invoice {period_start}..{prev_end} sales={sales}",
            )
        )
        if not is_zero and notices is not None:
            notices.append((arr.store_id, "FeeInvoiceRaised", None))
        created += 1

    await session.flush()
    return created
