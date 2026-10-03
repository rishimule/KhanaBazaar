# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date, datetime, timedelta, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import User
from app.models.commerce import Order, OrderStatus, Payment, PaymentStatus
from app.models.courier import OrderCourier
from tests._courier_helpers import (
    ADMIN,
    CUSTOMER,
    SELLER,
    client_as,
    insert_courier_order,
    seed_courier_world,
)


async def _ids(user: User, query: str) -> set[int]:
    async with client_as(user) as ac:
        resp = await ac.get(f"/api/v1/orders?{query}")
    assert resp.status_code == 200, resp.text
    return {o["id"] for o in resp.json()["orders"]}


async def test_needs_filters(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    pending = await insert_courier_order(session, world)
    quoted = await insert_courier_order(session, world, status=OrderStatus.Quoted, quote_fee=120.0)
    claimed = await insert_courier_order(session, world, status=OrderStatus.Accepted, claimed=True)
    unclaimed = await insert_courier_order(session, world, status=OrderStatus.Accepted)
    refund = await insert_courier_order(
        session, world, status=OrderStatus.Cancelled, payment_status=PaymentStatus.Paid,
    )
    async with client_as(CUSTOMER) as ac:
        door = (await ac.post("/api/v1/orders", json={
            "customer_address_id": world.local_address_id, "store_id": world.store_id,
            "service_id": world.service_id, "payment_method": "upi",
        })).json()["id"]

    assert await _ids(SELLER, "needs=quote") == {pending}
    assert await _ids(SELLER, "needs=payment_check") == {claimed}
    assert await _ids(SELLER, "needs=refund") == {refund}
    assert await _ids(SELLER, "delivery_mode=courier") == {pending, quoted, claimed, unclaimed, refund}
    assert door not in await _ids(ADMIN, "delivery_mode=courier")


async def test_stale_filter(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    old = await insert_courier_order(session, world)
    fresh = await insert_courier_order(session, world)
    row = await session.get(Order, old)
    assert row is not None
    row.placed_at = datetime.now(timezone.utc) - timedelta(days=4)
    await session.commit()
    ids = await _ids(ADMIN, "stale=true")
    assert old in ids and fresh not in ids


async def test_stale_filter_covers_accepted_and_overdue_shipments(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    now = datetime.now(timezone.utc)
    accepted_old = await insert_courier_order(session, world, status=OrderStatus.Accepted)
    accepted_claimed = await insert_courier_order(session, world, status=OrderStatus.Accepted)
    overdue = await insert_courier_order(
        session, world, status=OrderStatus.Dispatched, payment_status=PaymentStatus.Paid,
    )
    paid_old = await insert_courier_order(
        session, world, status=OrderStatus.Paid, payment_status=PaymentStatus.Paid,
    )
    rows = {
        r.order_id: r
        for r in (await session.exec(select(OrderCourier))).all()
    }
    rows[accepted_old].accepted_at = now - timedelta(days=4)
    # Accepted long ago, but the customer claimed yesterday: the stage moved.
    rows[accepted_claimed].accepted_at = now - timedelta(days=4)
    claimed = (await session.exec(select(Payment).where(Payment.order_id == accepted_claimed))).one()
    claimed.customer_claimed_at = now - timedelta(days=1)
    rows[overdue].eta_to = date.today() - timedelta(days=5)
    paid_order = await session.get(Order, paid_old)
    assert paid_order is not None
    paid_order.placed_at = now - timedelta(days=10)
    await session.commit()
    ids = await _ids(ADMIN, "stale=true")
    assert accepted_old in ids and overdue in ids
    assert accepted_claimed not in ids
    assert paid_old not in ids  # the seller holds the money: not a stall (documented gap)


async def test_invalid_needs_is_rejected(session: AsyncSession) -> None:
    await seed_courier_world(session)
    async with client_as(SELLER) as ac:
        resp = await ac.get("/api/v1/orders?needs=everything")
    assert resp.status_code == 422
