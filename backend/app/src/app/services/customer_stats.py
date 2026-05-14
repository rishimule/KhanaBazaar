# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, func
from sqlalchemy import select as sa_select
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Order, OrderStatus
from app.models.store import Store
from app.schemas.customer_stats import CustomerStatsResponse, OrderSummary

# IST is UTC+5:30 — month boundaries should match the customer's local calendar.
_IST = timezone(timedelta(hours=5, minutes=30))


def _start_of_month_utc(now: datetime) -> datetime:
    """Return the first instant of the current IST month, expressed in UTC."""
    ist_now = now.astimezone(_IST)
    ist_start = ist_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return ist_start.astimezone(timezone.utc)


async def compute_stats(
    session: AsyncSession, customer_profile_id: int
) -> CustomerStatsResponse:
    now = datetime.now(timezone.utc)
    month_start = _start_of_month_utc(now)

    orders_this_month_q = (
        sa_select(func.count())  # type: ignore[arg-type]
        .select_from(Order)
        .where(Order.customer_profile_id == customer_profile_id)  # type: ignore[arg-type]
        .where(Order.placed_at >= month_start)  # type: ignore[arg-type]
    )
    orders_this_month = (await session.execute(orders_this_month_q)).scalar() or 0

    lifetime_spend_q = (
        sa_select(func.coalesce(func.sum(Order.total), 0))  # type: ignore[arg-type]
        .where(Order.customer_profile_id == customer_profile_id)  # type: ignore[arg-type]
        .where(Order.status == OrderStatus.Delivered)  # type: ignore[arg-type]
    )
    lifetime_spend = float((await session.execute(lifetime_spend_q)).scalar() or 0)

    fav_q = (
        sa_select(  # type: ignore[call-overload]
            Order.store_id,
            func.count().label("c"),
            func.max(Order.placed_at).label("recent"),
        )
        .where(Order.customer_profile_id == customer_profile_id)  # type: ignore[arg-type]
        .where(Order.status == OrderStatus.Delivered)  # type: ignore[arg-type]
        .group_by(Order.store_id)
        .order_by(desc("c"), desc("recent"))
        .limit(1)
    )
    fav_row = (await session.execute(fav_q)).first()
    favorite_store_id: int | None = fav_row[0] if fav_row else None

    recent_q = (
        select(Order)
        .where(Order.customer_profile_id == customer_profile_id)  # type: ignore[arg-type]
        .where(Order.status == OrderStatus.Delivered)  # type: ignore[arg-type]
        .order_by(desc(Order.placed_at), desc(Order.id))  # type: ignore[arg-type]
        .limit(3)
    )
    recent_orders = list((await session.exec(recent_q)).all())

    store_ids: set[int] = {o.store_id for o in recent_orders}
    if favorite_store_id is not None:
        store_ids.add(favorite_store_id)

    name_by_store: dict[int, str] = {}
    if store_ids:
        name_rows = (
            await session.execute(
                sa_select(Store.id, Store.name).where(Store.id.in_(store_ids))  # type: ignore[union-attr,call-overload]
            )
        ).all()
        for sid, nm in name_rows:
            if sid is not None:
                name_by_store[sid] = nm

    favorite_store_name = (
        name_by_store.get(favorite_store_id) if favorite_store_id is not None else None
    )

    return CustomerStatsResponse(
        orders_this_month=int(orders_this_month),
        lifetime_spend=lifetime_spend,
        favorite_store_id=favorite_store_id,
        favorite_store_name=favorite_store_name,
        recent_delivered=[
            OrderSummary(
                id=int(o.id) if o.id is not None else 0,
                store_id=o.store_id,
                store_name=name_by_store.get(o.store_id, ""),
                service_id=o.service_id,
                service_name=o.service_name_snapshot,
                total=o.total,
                placed_at=o.placed_at,
            )
            for o in recent_orders
        ],
    )
