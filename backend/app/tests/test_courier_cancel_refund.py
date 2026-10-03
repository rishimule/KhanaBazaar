# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Any

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.notification import Notification
from app.models.returns import CustomerStoreCredit
from app.models.store import StoreInventory
from tests._courier_helpers import (
    ADMIN,
    CUSTOMER,
    SELLER,
    CourierWorld,
    accept_quote,
    claim_payment,
    client_as,
    get_order,
    grant_store_credit,
    order_at_dispatched,
    order_at_paid,
    place_courier_order,
    seed_courier_world,
    send_quote,
)

REASON = "No courier serves this PIN code"


async def _cancel(order_id: int, user: Any, **body: Any) -> httpx.Response:
    async with client_as(user) as ac:
        return await ac.post(f"/api/v1/orders/{order_id}/cancel", json=body or None)


async def _accepted(world: CourierWorld) -> int:
    order = await place_courier_order(world)
    quote = (await send_quote(order["id"])).json()["courier"]["quotes"][0]
    assert (await accept_quote(order["id"], quote["id"])).status_code == 200
    return int(order["id"])


async def _stock(session: AsyncSession, world: CourierWorld) -> int:
    inv = await session.get(StoreInventory, world.inventory_id)
    assert inv is not None
    await session.refresh(inv)
    return inv.stock


async def test_customer_declines_a_quote_and_the_seller_hears(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    await send_quote(order["id"])
    resp = await _cancel(order["id"], CUSTOMER, reason="Courier charge too high")
    assert resp.status_code == 200, resp.text
    courier = resp.json()["courier"]
    assert (courier["cancel_reason"], courier["cancelled_by"]) == ("Courier charge too high", "customer")
    assert await _stock(session, world) == 10  # restocked
    rows = (await session.exec(select(Notification).where(Notification.order_id == order["id"]))).all()
    assert "courier_customer_cancelled" in [r.status_value for r in rows]


async def test_customer_can_cancel_until_they_say_they_paid(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await _accepted(world)
    assert (await _cancel(order_id, CUSTOMER)).status_code == 200


async def test_claimed_customer_cannot_cancel(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await _accepted(world)
    await claim_payment(order_id, "upi")
    resp = await _cancel(order_id, CUSTOMER)
    assert resp.status_code == 403 and resp.json()["detail"] == "cancel_not_allowed"


async def test_customer_cannot_cancel_a_paid_order(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_paid(world)
    resp = await _cancel(order["id"], CUSTOMER)
    assert resp.status_code == 403


async def test_seller_needs_a_reason(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    bare = await _cancel(order["id"], SELLER)
    assert bare.status_code == 422 and bare.json()["detail"]["code"] == "reason_required"
    assert (await _cancel(order["id"], SELLER, reason=REASON)).status_code == 200


async def test_seller_cannot_cancel_a_shipped_order(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_dispatched(world)
    resp = await _cancel(order["id"], SELLER, reason=REASON)
    assert resp.status_code == 403 and resp.json()["detail"] == "cancel_not_allowed"


async def test_paid_cancellation_leaves_a_refund_due(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_paid(world)
    resp = await _cancel(order["id"], SELLER, reason=REASON)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["payment"]["status"] == "paid"  # never flipped to refunded here
    assert body["courier"]["refund_due"] is True
    customer_row = (await session.exec(select(Notification).where(
        Notification.order_id == order["id"], Notification.status_value == "cancelled",
    ))).one()
    assert "refund of ₹320.00" in customer_row.body


async def test_admin_cancel_after_shipping_does_not_restock(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_dispatched(world)
    resp = await _cancel(order["id"], ADMIN, reason="Parcel lost by the courier")
    assert resp.status_code == 200, resp.text
    assert resp.json()["courier"]["refund_due"] is True
    assert await _stock(session, world) == 8  # the parcel is gone


async def test_claimed_unconfirmed_cancel_asks_whether_money_arrived(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await _accepted(world)
    await claim_payment(order_id, "upi")
    missing = await _cancel(order_id, SELLER, reason=REASON)
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "payment_received_required"
    resp = await _cancel(order_id, SELLER, reason=REASON, payment_received=True)
    assert resp.status_code == 200 and resp.json()["courier"]["refund_due"] is True


async def test_seller_says_the_money_never_arrived(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await _accepted(world)
    await claim_payment(order_id, "upi")
    resp = await _cancel(order_id, SELLER, reason=REASON, payment_received=False)
    body = resp.json()
    assert body["courier"]["refund_due"] is False
    assert body["courier"]["payment_reported_missing_at"] is not None
    assert body["payment"]["status"] == "pending"


async def test_refund_sent_closes_the_refund(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_paid(world)
    await _cancel(order["id"], SELLER, reason=REASON)
    async with client_as(SELLER) as ac:
        sent = await ac.post(
            f"/api/v1/orders/{order['id']}/payment/refund-sent", json={"reference": "UTR998877"},
        )
        again = await ac.post(f"/api/v1/orders/{order['id']}/payment/refund-sent")
    assert sent.status_code == 200, sent.text
    payment = sent.json()["payment"]
    assert (payment["status"], payment["refund_reference"]) == ("refunded", "UTR998877")
    assert payment["refunded_at"] is not None
    assert sent.json()["courier"]["refund_due"] is False
    assert again.status_code == 409 and again.json()["detail"]["code"] == "already_refunded"
    rows = (await session.exec(select(Notification).where(Notification.order_id == order["id"]))).all()
    assert "courier_refund_sent" in [r.status_value for r in rows]


async def test_refund_sent_needs_a_refund_due(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_paid(world)
    async with client_as(SELLER) as ac:
        resp = await ac.post(f"/api/v1/orders/{order['id']}/payment/refund-sent")
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "refund_not_due"


async def test_admin_refund_marker_stamps_who_and_when(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_paid(world)
    await _cancel(order["id"], SELLER, reason=REASON)
    async with client_as(ADMIN) as ac:
        resp = await ac.post(
            f"/api/v1/admin/orders/{order['id']}/refund",
            json={"reason": "Seller refunded by phone, confirmed"},
        )
    assert resp.status_code == 200, resp.text
    payment = (await get_order(order["id"]))["payment"]
    assert payment["status"] == "refunded" and payment["refunded_at"] is not None


async def test_cancel_returns_both_store_credit_spends(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await grant_store_credit(session, world, 250.0)
    order_id = await _accepted(world)  # 200 at placement + 50 top-up
    assert (await _cancel(order_id, CUSTOMER)).status_code == 200
    account = (await session.exec(select(CustomerStoreCredit).where(
        CustomerStoreCredit.customer_profile_id == world.customer_profile_id,
    ))).one()
    await session.refresh(account)
    assert account.balance == 250.0
