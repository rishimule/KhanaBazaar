# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from unittest.mock import MagicMock, patch

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Delivery
from app.models.notification import Notification
from tests._courier_helpers import (
    ADMIN,
    CUSTOMER,
    SELLER,
    client_as,
    get_order,
    order_at_dispatched,
    order_at_paid,
    seed_courier_world,
)

TRACKING = {
    "carrier_name": "Delhivery",
    "tracking_number": "DLV123456",
    "tracking_url": "https://www.delhivery.com/track/package/DLV123456",
}


async def _statuses(session: AsyncSession, order_id: int) -> list[str]:
    rows = (await session.exec(select(Notification).where(Notification.order_id == order_id))).all()
    return [r.status_value for r in rows]


async def test_ship_with_tracking_and_no_otp(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_dispatched(world, **TRACKING)
    assert order["status"] == "dispatched"
    courier = order["courier"]
    assert (courier["carrier_name"], courier["tracking_number"]) == ("Delhivery", "DLV123456")
    assert courier["tracking_url"] == TRACKING["tracking_url"]
    delivery = (await session.exec(select(Delivery).where(Delivery.order_id == order["id"]))).one()
    assert delivery.delivery_otp is None
    shipped = (await session.exec(select(Notification).where(
        Notification.order_id == order["id"], Notification.status_value == "dispatched",
    ))).one()
    assert "Delhivery · DLV123456" in shipped.body


async def test_carrier_defaults_to_the_quote(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_dispatched(world)
    assert order["courier"]["carrier_name"] == "DTDC"


async def test_a_blanked_carrier_on_shipping_stays_blank(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_dispatched(world, carrier_name="")
    assert order["courier"]["carrier_name"] is None


async def test_tracking_url_must_be_https_without_credentials(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_paid(world)
    async with client_as(SELLER) as ac:
        await ac.post(f"/api/v1/orders/{order['id']}/transition", json={"to": "packed"})
        plain = await ac.post(f"/api/v1/orders/{order['id']}/transition", json={
            "to": "dispatched", "tracking_url": "http://track.example/1",
        })
        creds = await ac.post(f"/api/v1/orders/{order['id']}/transition", json={
            "to": "dispatched", "tracking_url": "https://user:pw@track.example/1",
        })
    assert plain.status_code == 422 and plain.json()["detail"]["code"] == "invalid_tracking_url"
    assert creds.status_code == 422


async def test_tracking_fields_only_on_courier_dispatch(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_paid(world)
    async with client_as(SELLER) as ac:
        resp = await ac.post(f"/api/v1/orders/{order['id']}/transition", json={
            "to": "packed", "tracking_number": "X1",
        })
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "courier_fields_not_allowed"


async def test_tracking_can_be_edited_after_shipping(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_dispatched(world)
    async with client_as(SELLER) as ac:
        changed = await ac.patch(f"/api/v1/orders/{order['id']}/courier/tracking", json=TRACKING)
        same = await ac.patch(f"/api/v1/orders/{order['id']}/courier/tracking", json=TRACKING)
    assert changed.status_code == 200, changed.text
    assert changed.json()["courier"]["tracking_number"] == "DLV123456"
    assert same.status_code == 200
    assert (await _statuses(session, order["id"])).count("courier_tracking_updated") == 1


async def test_tracking_edit_needs_a_shipped_order(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_paid(world)
    async with client_as(SELLER) as ac:
        resp = await ac.patch(f"/api/v1/orders/{order['id']}/courier/tracking", json=TRACKING)
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "not_dispatched"


async def test_seller_marks_delivered_without_otp(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_dispatched(world)
    paid_at = order["payment"]["paid_at"]
    async with client_as(SELLER) as ac:
        resp = await ac.post(f"/api/v1/orders/{order['id']}/transition", json={"to": "delivered"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "delivered"
    assert body["courier"]["delivered_by"] == "seller"
    assert body["payment"]["paid_at"] == paid_at  # paid at confirmation, not delivery


async def test_customer_marks_received(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_dispatched(world)
    review = MagicMock()
    with patch("app.api.orders.dispatch_order_review_request", review):
        async with client_as(CUSTOMER) as ac:
            resp = await ac.post(f"/api/v1/orders/{order['id']}/courier/received")
    assert resp.status_code == 200, resp.text
    assert resp.json()["courier"]["delivered_by"] == "customer"
    review.assert_called_once_with(order["id"])
    assert "courier_customer_received" in await _statuses(session, order["id"])


async def test_second_delivery_mark_is_rejected(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_dispatched(world)
    async with client_as(CUSTOMER) as ac:
        assert (await ac.post(f"/api/v1/orders/{order['id']}/courier/received")).status_code == 200
        again = await ac.post(f"/api/v1/orders/{order['id']}/courier/received")
    async with client_as(SELLER) as ac:
        seller = await ac.post(f"/api/v1/orders/{order['id']}/transition", json={"to": "delivered"})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "already_delivered"
    assert seller.status_code == 409 and seller.json()["detail"]["code"] == "already_delivered"


async def test_admin_force_delivers_with_a_reason(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_dispatched(world)
    async with client_as(ADMIN) as ac:
        bare = await ac.post(f"/api/v1/orders/{order['id']}/transition", json={"to": "delivered"})
        ok = await ac.post(f"/api/v1/orders/{order['id']}/transition", json={
            "to": "delivered", "reason": "Courier confirmed delivery by phone",
        })
    assert bare.status_code == 422
    assert ok.status_code == 200 and ok.json()["courier"]["delivered_by"] == "admin"


async def test_delivery_otp_resend_is_not_offered(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await order_at_dispatched(world)
    async with client_as(CUSTOMER) as ac:
        resp = await ac.post(f"/api/v1/orders/{order['id']}/delivery-otp/resend")
    assert resp.status_code == 409
    assert (await get_order(order["id"]))["delivery"]["otp"] is None
