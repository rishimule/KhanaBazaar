# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Live receipt issuing on the transition path (spec 2026-10-10 §2.2, §4)."""
import logging
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_user
from app.models.base import User
from app.models.commerce import DeliveryMode, Order
from app.models.receipt import OrderReceipt, OrderReceiptCounter
from app.services.receipts import (
    _next_seq,
    fiscal_year_for,
    format_receipt_number,
    issue_missing,
)
from tests.test_orders import (  # noqa: F401
    _deliver_with_otp,
    _order_id_for_store,
    _place_orders,
    as_customer,
    mock_admin,
    mock_seller,
    seed,
)


async def _receipts(session: AsyncSession, order_id: int) -> list[OrderReceipt]:
    rows = await session.exec(select(OrderReceipt).where(OrderReceipt.order_id == order_id))
    return list(rows.all())


async def _counters(session: AsyncSession) -> list[OrderReceiptCounter]:
    return list((await session.exec(select(OrderReceiptCounter))).all())


def _expected_number(seq: int) -> str:
    return format_receipt_number(fiscal_year_for(datetime.now(timezone.utc)), seq)


def _client_as(user: User) -> AsyncClient:
    app.dependency_overrides[get_current_user] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_door_delivery_issues_one_receipt(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])
    async with _client_as(mock_seller) as ac:
        resp = await _deliver_with_otp(ac, target)
    assert resp.status_code == 200, resp.text

    [receipt] = await _receipts(session, target)
    assert receipt.number == _expected_number(1)
    assert receipt.store_id == seed["store_a"] and receipt.issued_via == "delivery"
    assert receipt.snapshot["order"]["id"] == target
    # Delivery marked the UPI payment paid in the same transaction, before the snapshot.
    assert receipt.snapshot["payment"]["settled"] == "paid"
    assert receipt.snapshot["seller"]["business_name"] == "S1 Store"


async def test_each_store_has_its_own_series(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    order_ids = await _place_orders(seed)
    order_a = await _order_id_for_store(order_ids, seed["store_a"])
    order_b = await _order_id_for_store(order_ids, seed["store_b"])
    async with _client_as(mock_seller) as ac:
        assert (await _deliver_with_otp(ac, order_a)).status_code == 200
    # Admin force-deliver is the fifth delivery path; it issues too.
    async with _client_as(mock_admin) as ac:
        await ac.post(f"/api/v1/orders/{order_b}/transition", json={"to": "packed"})
        await ac.post(f"/api/v1/orders/{order_b}/transition", json={"to": "dispatched"})
        forced = await ac.post(
            f"/api/v1/orders/{order_b}/transition",
            json={"to": "delivered", "reason": "customer confirmed by phone"},
        )
    assert forced.status_code == 200, forced.text
    [ra] = await _receipts(session, order_a)
    [rb] = await _receipts(session, order_b)
    assert ra.number == _expected_number(1) and rb.number == _expected_number(1)
    assert ra.store_id != rb.store_id


async def test_counter_numbers_follow_on(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    store = seed["store_a"]
    assert [await _next_seq(session, store, 2026) for _ in range(3)] == [1, 2, 3]
    assert await _next_seq(session, store, 2025) == 1
    assert await _next_seq(session, seed["store_b"], 2026) == 1


async def test_wrong_code_takes_no_number(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])
    async with _client_as(mock_seller) as ac:
        await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "packed"})
        await ac.post(f"/api/v1/orders/{target}/transition", json={"to": "dispatched"})
        bad = await ac.post(
            f"/api/v1/orders/{target}/transition", json={"to": "delivered", "otp": "000000"}
        )
    assert bad.status_code == 422
    assert await _receipts(session, target) == []
    assert await _counters(session) == []


async def test_receipt_failure_never_blocks_delivery(
    as_customer: Any,
    seed: dict[str, int],
    session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])
    # Fails AFTER the number is taken: the savepoint must hand it back.
    with (
        caplog.at_level(logging.ERROR, logger="app.services.receipts"),
        patch("app.services.receipts.format_receipt_number", side_effect=RuntimeError("boom")),
    ):
        async with _client_as(mock_seller) as ac:
            resp = await _deliver_with_otp(ac, target)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "delivered"
    assert await _receipts(session, target) == []
    assert await _counters(session) == []
    assert f"receipt_issue_failed order_id={target}" in caplog.text

    # The hourly sweep repairs it, numbered from the start of the series.
    assert await issue_missing(session) == (1, 0)
    [receipt] = await _receipts(session, target)
    assert receipt.issued_via == "backfill" and receipt.number == _expected_number(1)


async def test_database_error_in_the_savepoint_spares_the_delivery(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])
    # A receipt already on file makes the live insert hit the unique order_id
    # index at flush time: a real IntegrityError inside the savepoint.
    session.add(
        OrderReceipt(
            order_id=target,
            store_id=seed["store_a"],
            fiscal_year=2020,
            seq=1,
            number="RC-2021-000001",
            issued_at=datetime(2020, 5, 1, tzinfo=timezone.utc),
            issued_via="backfill",
            snapshot={"version": 1},
        )
    )
    await session.commit()
    async with _client_as(mock_seller) as ac:
        resp = await _deliver_with_otp(ac, target)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "delivered"
    assert [r.number for r in await _receipts(session, target)] == ["RC-2021-000001"]
    assert await _counters(session) == []


async def test_pickup_delivery_issues_receipt_without_deliver_to(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])
    # Pickup runs the same transition + handover-code path as door delivery.
    order = await session.get(Order, target)
    assert order is not None
    order.delivery_mode = DeliveryMode.Pickup
    session.add(order)
    await session.commit()
    async with _client_as(mock_seller) as ac:
        assert (await _deliver_with_otp(ac, target)).status_code == 200
    [receipt] = await _receipts(session, target)
    assert receipt.snapshot["order"]["delivery_mode"] == "pickup"
    assert receipt.snapshot["deliver_to"] is None
