# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Seller-side eligibility: the seller needs the same returnable-line view the
customer gets before starting a return on their behalf."""
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import OrderStatus
from tests._returns_helpers import (
    as_seller,
    clear_overrides,
    seed_delivered_order,
)


@pytest.fixture(autouse=True)
def _cleanup() -> Any:
    yield
    clear_overrides()


async def test_seller_sees_returnable_lines(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, delivered_days_ago=1, return_window_days=7)
    as_seller(seed.seller_user)

    resp = await client.get(f"/api/v1/sellers/me/returns/eligibility/{seed.order_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["eligible"] is True
    assert body["customer_profile_id"] == seed.customer_profile_id
    assert [line["returnable"] for line in body["lines"]] == [True, True]
    assert body["full_order_available"] is True


async def test_seller_window_closed_reports_reason(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, delivered_days_ago=30, return_window_days=7)
    as_seller(seed.seller_user)

    body = (
        await client.get(f"/api/v1/sellers/me/returns/eligibility/{seed.order_id}")
    ).json()
    assert body["eligible"] is False
    assert body["reason_code"] == "return_window_closed"


async def test_seller_undelivered_order_reports_reason(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, order_status=OrderStatus.Packed)
    as_seller(seed.seller_user)

    body = (
        await client.get(f"/api/v1/sellers/me/returns/eligibility/{seed.order_id}")
    ).json()
    assert body["eligible"] is False
    assert body["reason_code"] == "order_not_delivered"


async def test_another_sellers_order_is_404(
    session: AsyncSession, client: AsyncClient
) -> None:
    mine = await seed_delivered_order(session, email_suffix="mine")
    theirs = await seed_delivered_order(session, email_suffix="theirs")
    as_seller(mine.seller_user)

    resp = await client.get(
        f"/api/v1/sellers/me/returns/eligibility/{theirs.order_id}"
    )
    assert resp.status_code == 404


async def test_missing_order_is_404(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    as_seller(seed.seller_user)
    resp = await client.get("/api/v1/sellers/me/returns/eligibility/999999")
    assert resp.status_code == 404
