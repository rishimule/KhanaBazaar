# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timedelta, timezone

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import User
from app.models.commerce import Order, OrderStatus, PaymentStatus
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


async def test_invalid_needs_is_rejected(session: AsyncSession) -> None:
    await seed_courier_world(session)
    async with client_as(SELLER) as ac:
        resp = await ac.get("/api/v1/orders?needs=everything")
    assert resp.status_code == 422
