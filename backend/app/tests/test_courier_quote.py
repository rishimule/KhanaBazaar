# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.notification import Notification
from tests._courier_helpers import (
    ADMIN,
    CUSTOMER,
    OTHER_SELLER,
    SELLER,
    client_as,
    get_order,
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


async def test_a_failed_notification_does_not_fail_a_saved_quote(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The notify helper rolls the request session back on failure, which
    expires every object loaded through it — including the user, as it is in
    production (client_as injects a detached one, so load it via the session)."""
    from fastapi import Depends

    from app import app
    from app.core.security import get_current_user
    from app.db.session import get_db_session
    from app.models.base import User
    from app.services import courier_comms

    world = await seed_courier_world(session)
    order = await place_courier_order(world)

    async def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("notification store down")

    async def _session_user(db: AsyncSession = Depends(get_db_session)) -> User:
        user = await db.get(User, SELLER.id)
        assert user is not None
        return user

    monkeypatch.setattr(courier_comms, "record_order_status_notification", _boom)
    app.dependency_overrides[get_current_user] = _session_user
    try:
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(f"/api/v1/orders/{order['id']}/courier/quote", json={
                "courier_fee": 120, "eta_min_days": 3, "eta_max_days": 5,
            })
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "quoted"
