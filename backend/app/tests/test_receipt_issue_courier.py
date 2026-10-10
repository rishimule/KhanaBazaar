# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Live receipt issuing on the courier delivery paths (spec 2026-10-10 §1, §4)."""
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.receipt import OrderReceipt
from tests._courier_helpers import (
    CUSTOMER,
    SELLER,
    client_as,
    order_at_dispatched,
    seed_courier_world,
)


async def _receipts(session: AsyncSession, order_id: int) -> list[OrderReceipt]:
    rows = await session.exec(select(OrderReceipt).where(OrderReceipt.order_id == order_id))
    return list(rows.all())


async def test_customer_received_issues_receipt(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_dispatched(world)
    async with client_as(CUSTOMER) as ac:
        resp = await ac.post(f"/api/v1/orders/{order['id']}/courier/received")
    assert resp.status_code == 200, resp.text
    [receipt] = await _receipts(session, order["id"])
    snap = receipt.snapshot
    assert snap["amounts"]["delivery_fee_kind"] == "courier"
    assert snap["amounts"]["delivery_fee"] == 120.0
    assert snap["deliver_to"]["name"] is not None
    assert snap["payment"]["settled"] == "paid"


async def test_seller_marked_delivered_issues_receipt(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_dispatched(world)
    async with client_as(SELLER) as ac:
        resp = await ac.post(f"/api/v1/orders/{order['id']}/transition", json={"to": "delivered"})
    assert resp.status_code == 200, resp.text
    assert len(await _receipts(session, order["id"])) == 1


async def test_second_delivery_mark_issues_nothing_more(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_dispatched(world)
    async with client_as(CUSTOMER) as ac:
        assert (await ac.post(f"/api/v1/orders/{order['id']}/courier/received")).status_code == 200
    async with client_as(SELLER) as ac:
        again = await ac.post(f"/api/v1/orders/{order['id']}/transition", json={"to": "delivered"})
    assert again.status_code == 409
    assert len(await _receipts(session, order["id"])) == 1
