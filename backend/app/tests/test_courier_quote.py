# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.notification import Notification
from tests._courier_helpers import (
    ADMIN,
    CUSTOMER,
    OTHER_SELLER,
    SELLER,
    CourierWorld,
    client_as,
    get_order,
    order_at_paid,
    place_courier_order,
    seed_courier_world,
    send_quote,
)


async def _statuses(session: AsyncSession, order_id: int) -> list[str]:
    rows = (await session.exec(select(Notification).where(Notification.order_id == order_id))).all()
    return [r.status_value for r in rows]


async def test_seller_quotes_and_the_customer_is_told(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    resp = await send_quote(order["id"], note="Packed in a gift box")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "quoted"
    quote = body["courier"]["quotes"][0]
    assert (quote["version"], quote["courier_fee"], quote["eta_min_days"], quote["eta_max_days"]) == (1, 120.0, 3, 5)
    assert quote["note"] == "Packed in a gift box"
    assert body["total"] == 200.0  # the charge reaches the order only on acceptance
    assert "courier_quote_ready" in await _statuses(session, order["id"])


async def test_revisions_keep_history_for_the_seller_only(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    await send_quote(order["id"], fee=120.0)
    revised = await send_quote(order["id"], fee=150.0)
    assert revised.status_code == 200, revised.text
    seller_view = await get_order(order["id"], as_user=SELLER)
    customer_view = await get_order(order["id"])
    assert [q["version"] for q in seller_view["courier"]["quotes"]] == [2, 1]
    assert [q["courier_fee"] for q in customer_view["courier"]["quotes"]] == [150.0]
    assert customer_view["courier"]["revised"] is True
    assert "courier_quote_revised" in await _statuses(session, order["id"])


async def test_quote_versions_are_capped(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "COURIER_MAX_QUOTE_VERSIONS", 2)
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    # Different fees: an identical quote seconds later is a retry (see below).
    assert (await send_quote(order["id"], fee=120.0)).status_code == 200
    assert (await send_quote(order["id"], fee=130.0)).status_code == 200
    third = await send_quote(order["id"], fee=140.0)
    assert third.status_code == 409 and third.json()["detail"]["code"] == "too_many_quote_versions"


async def test_only_the_owning_seller_can_quote(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    for user in (CUSTOMER, OTHER_SELLER, ADMIN):
        resp = await send_quote(order["id"], as_user=user)
        assert resp.status_code == 403, user.email


async def test_quote_validation(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    assert (await send_quote(order["id"], min_days=6, max_days=3)).status_code == 422
    assert (await send_quote(order["id"], fee=-1)).status_code == 422
    assert (await send_quote(order["id"], max_days=61)).status_code == 422


async def test_door_orders_cannot_be_quoted(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    async with client_as(CUSTOMER) as ac:
        door = await ac.post("/api/v1/orders", json={
            "customer_address_id": world.local_address_id, "store_id": world.store_id,
            "service_id": world.service_id, "payment_method": "upi",
        })
    assert door.status_code == 201, door.text
    resp = await send_quote(door.json()["id"])
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "not_a_courier_order"
    assert (await get_order(door.json()["id"]))["courier"] is None


async def test_cancelled_orders_cannot_be_quoted(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    async with client_as(CUSTOMER) as ac:
        assert (await ac.post(f"/api/v1/orders/{order['id']}/cancel")).status_code == 200
    resp = await send_quote(order["id"])
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "terminal_status"


async def test_courier_orders_cannot_skip_the_quote(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    async with client_as(SELLER) as ac:
        resp = await ac.post(f"/api/v1/orders/{order['id']}/transition", json={"to": "packed"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["detail"] == "illegal_transition"


async def test_repeating_the_latest_quote_seconds_later_is_a_no_op(session: AsyncSession) -> None:
    # A double tap / retried request must not burn a version, tell the
    # customer the quote was "updated", or supersede the copy they may accept.
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    first = (await send_quote(order["id"])).json()["courier"]["quotes"][0]
    again = await send_quote(order["id"])
    assert again.status_code == 200, again.text
    quotes = again.json()["courier"]["quotes"]
    assert [(q["id"], q["version"]) for q in quotes] == [(first["id"], 1)]
    statuses = await _statuses(session, order["id"])
    assert statuses.count("courier_quote_ready") == 1
    assert "courier_quote_revised" not in statuses


async def test_order_carries_the_quote_version_cap(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    body = (await send_quote(order["id"])).json()
    assert body["courier"]["max_quote_versions"] == settings.COURIER_MAX_QUOTE_VERSIONS


@asynccontextmanager
async def _session_bound_client(user_id: int) -> AsyncIterator[AsyncClient]:
    """Like client_as, but the user is loaded through the request's own
    session, as get_current_user does in production — so a rollback inside
    the request expires it too (client_as injects a detached user)."""
    from app import app
    from app.core.security import get_current_user
    from app.db.session import get_db_session
    from app.models.base import User

    async def _session_user(db: AsyncSession = Depends(get_db_session)) -> User:
        user = await db.get(User, user_id)
        assert user is not None
        return user

    app.dependency_overrides[get_current_user] = _session_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def _boom(*args: object, **kwargs: object) -> None:
    raise RuntimeError("notification store down")


async def test_a_failed_notification_does_not_fail_a_saved_quote(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The courier notify helper rolls the request session back on failure."""
    from app.services import courier_comms

    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    monkeypatch.setattr(courier_comms, "record_order_status_notification", _boom)
    async with _session_bound_client(int(SELLER.id or 0)) as ac:
        resp = await ac.post(f"/api/v1/orders/{order['id']}/courier/quote", json={
            "courier_fee": 120, "eta_min_days": 3, "eta_max_days": 5,
        })
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "quoted"


async def test_a_failed_status_notification_does_not_fail_a_saved_transition_or_cancel(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """record_and_dispatch_notification rolls back on failure; the route must
    still serialise the (reloaded) order instead of answering 500."""
    from app.api import orders as orders_api

    world = await seed_courier_world(session)
    paid = await order_at_paid(world)
    monkeypatch.setattr(orders_api, "record_order_status_notification", _boom)
    async with _session_bound_client(int(SELLER.id or 0)) as ac:
        packed = await ac.post(f"/api/v1/orders/{paid['id']}/transition", json={"to": "packed"})
        cancelled = await ac.post(f"/api/v1/orders/{paid['id']}/cancel", json={
            "reason": "Item damaged while packing",
        })
    assert packed.status_code == 200, packed.text
    assert packed.json()["status"] == "packed"
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"


def _break_courier_comms(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both courier notify helpers roll the request session back on failure,
    expiring the request's user; a route reading `user.role` after that 500s."""
    from app.services import courier_comms

    monkeypatch.setattr(courier_comms, "record_order_status_notification", _boom)
    monkeypatch.setattr(courier_comms, "record_seller_notification", _boom)


async def _accepted_order(world: CourierWorld) -> int:
    order = await place_courier_order(world)
    quote = (await send_quote(order["id"])).json()["courier"]["quotes"][0]
    async with client_as(CUSTOMER) as ac:
        resp = await ac.post(
            f"/api/v1/orders/{order['id']}/courier/accept", json={"quote_id": quote["id"]}
        )
    assert resp.status_code == 200, resp.text
    return int(order["id"])


async def test_a_failed_notification_does_not_fail_payment_shipping_or_receipt(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = await seed_courier_world(session)
    order_id = await _accepted_order(world)
    _break_courier_comms(monkeypatch)
    async with _session_bound_client(int(SELLER.id or 0)) as ac:
        paid = await ac.post(f"/api/v1/orders/{order_id}/payment/confirm")
        assert paid.status_code == 200, paid.text
        for to in ("packed", "dispatched"):
            moved = await ac.post(f"/api/v1/orders/{order_id}/transition", json={"to": to})
            assert moved.status_code == 200, moved.text
        tracked = await ac.patch(
            f"/api/v1/orders/{order_id}/courier/tracking", json={"tracking_number": "AB123"}
        )
    assert tracked.status_code == 200, tracked.text
    async with _session_bound_client(int(CUSTOMER.id or 0)) as ac:
        received = await ac.post(f"/api/v1/orders/{order_id}/courier/received")
    assert received.status_code == 200, received.text
    assert received.json()["status"] == "delivered"


async def test_a_failed_notification_does_not_fail_a_missing_payment_report(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = await seed_courier_world(session)
    order_id = await _accepted_order(world)
    async with client_as(CUSTOMER) as ac:
        claimed = await ac.post(f"/api/v1/orders/{order_id}/payment/claim", json={"method": "upi"})
    assert claimed.status_code == 200, claimed.text
    _break_courier_comms(monkeypatch)
    async with _session_bound_client(int(SELLER.id or 0)) as ac:
        resp = await ac.post(f"/api/v1/orders/{order_id}/payment/not-received")
    assert resp.status_code == 200, resp.text
    assert resp.json()["payment"]["customer_claimed_at"] is None


async def test_a_failed_notification_does_not_fail_a_refund_record(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = await seed_courier_world(session)
    paid = await order_at_paid(world)
    async with client_as(SELLER) as ac:
        cancelled = await ac.post(
            f"/api/v1/orders/{paid['id']}/cancel", json={"reason": "Item damaged while packing"}
        )
    assert cancelled.status_code == 200, cancelled.text
    _break_courier_comms(monkeypatch)
    async with _session_bound_client(int(SELLER.id or 0)) as ac:
        sent = await ac.post(f"/api/v1/orders/{paid['id']}/payment/refund-sent")
    assert sent.status_code == 200, sent.text
    assert sent.json()["payment"]["status"] == "refunded"
