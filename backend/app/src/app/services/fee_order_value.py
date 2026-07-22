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

IST = ZoneInfo("Asia/Kolkata")


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
