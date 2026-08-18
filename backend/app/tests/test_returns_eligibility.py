# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import OrderStatus
from app.models.returns import (
    ReturnInitiator,
    ReturnReasonCode,
    ReturnRequest,
    ReturnRequestItem,
    ReturnSettlementChoice,
    ReturnStatus,
)
from tests._returns_helpers import as_customer, clear_overrides, seed_delivered_order


@pytest.fixture(autouse=True)
def _cleanup() -> Any:
    yield
    clear_overrides()


async def _lock_line(
    session: AsyncSession, seed: Any, order_item_id: int, status: ReturnStatus
) -> ReturnRequest:
    now = datetime.now(timezone.utc)
    req = ReturnRequest(
        order_id=seed.order_id, customer_profile_id=seed.customer_profile_id,
        store_id=seed.store_id, seller_profile_id=seed.seller_profile_id,
        service_id=seed.service_id, initiated_by=ReturnInitiator.customer,
        initiated_by_user_id=seed.customer_user.id, status=status,
        is_full_order=False, reason_code=ReturnReasonCode.damaged,
        items_amount=250.0, delivery_fee_amount=0.0, total_amount=250.0,
        settlement_choice=ReturnSettlementChoice.store_credit,
        agreement_policy_version=1, window_expires_at=now + timedelta(days=5),
        confirm_expires_at=now + timedelta(hours=48),
    )
    session.add(req)
    await session.flush()
    session.add(ReturnRequestItem(
        return_request_id=req.id, order_item_id=order_item_id, quantity=1,
        product_name_snapshot="Ghee 1L", unit_price_snapshot=250.0, line_total=250.0,
    ))
    await session.commit()
    return req


async def test_delivered_order_inside_window_is_eligible(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, delivered_days_ago=2, return_window_days=7)
    as_customer(seed.customer_user)

    resp = await client.get(f"/api/v1/returns/eligibility/{seed.order_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["eligible"] is True
    assert body["reason_code"] is None
    assert body["full_order_available"] is True
    assert body["delivery_fee"] == 20.0
    assert [line["returnable"] for line in body["lines"]] == [True, True]
    assert body["lines"][0]["line_total"] == 250.0
    assert body["lines"][1]["line_total"] == 600.0


async def test_window_closed_is_not_eligible(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, delivered_days_ago=9, return_window_days=7)
    as_customer(seed.customer_user)

    body = (await client.get(f"/api/v1/returns/eligibility/{seed.order_id}")).json()
    assert body["eligible"] is False
    assert body["reason_code"] == "return_window_closed"
    # The deadline is still reported so the UI can say when it passed.
    assert body["window_expires_at"] is not None


async def test_zero_window_disables_returns(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, return_window_days=0)
    as_customer(seed.customer_user)

    body = (await client.get(f"/api/v1/returns/eligibility/{seed.order_id}")).json()
    assert body["eligible"] is False
    assert body["reason_code"] == "returns_disabled_for_service"


async def test_undelivered_order_is_not_eligible(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, order_status=OrderStatus.Dispatched)
    as_customer(seed.customer_user)

    body = (await client.get(f"/api/v1/returns/eligibility/{seed.order_id}")).json()
    assert body["eligible"] is False
    assert body["reason_code"] == "order_not_delivered"


async def test_boundary_last_day_is_still_eligible(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, delivered_days_ago=6, return_window_days=7)
    as_customer(seed.customer_user)
    body = (await client.get(f"/api/v1/returns/eligibility/{seed.order_id}")).json()
    assert body["eligible"] is True


async def test_line_locked_by_active_return_is_not_returnable(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await _lock_line(session, seed, seed.order_item_ids[0], ReturnStatus.active)
    as_customer(seed.customer_user)

    body = (await client.get(f"/api/v1/returns/eligibility/{seed.order_id}")).json()
    assert body["eligible"] is True
    lines = {line["order_item_id"]: line for line in body["lines"]}
    assert lines[seed.order_item_ids[0]]["returnable"] is False
    assert lines[seed.order_item_ids[0]]["lock_reason"] == "already_in_return"
    assert lines[seed.order_item_ids[1]]["returnable"] is True
    assert body["full_order_available"] is False


async def test_rejected_return_releases_its_line(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await _lock_line(session, seed, seed.order_item_ids[0], ReturnStatus.rejected)
    as_customer(seed.customer_user)

    body = (await client.get(f"/api/v1/returns/eligibility/{seed.order_id}")).json()
    assert all(line["returnable"] for line in body["lines"])
    assert body["full_order_available"] is True


async def test_closed_return_keeps_full_order_unavailable(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await _lock_line(session, seed, seed.order_item_ids[0], ReturnStatus.closed)
    as_customer(seed.customer_user)

    body = (await client.get(f"/api/v1/returns/eligibility/{seed.order_id}")).json()
    assert body["full_order_available"] is False


async def test_all_lines_locked_reports_items_already_returned(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await _lock_line(session, seed, seed.order_item_ids[0], ReturnStatus.closed)
    await _lock_line(session, seed, seed.order_item_ids[1], ReturnStatus.closed)
    as_customer(seed.customer_user)

    body = (await client.get(f"/api/v1/returns/eligibility/{seed.order_id}")).json()
    assert body["eligible"] is False
    assert body["reason_code"] == "items_already_returned"


async def test_agreement_version_is_reported(
    session: AsyncSession, client: AsyncClient
) -> None:
    from tests._returns_helpers import publish_return_agreement

    seed = await seed_delivered_order(session)
    as_customer(seed.customer_user)
    before = (await client.get(f"/api/v1/returns/eligibility/{seed.order_id}")).json()
    assert before["agreement_version"] is None

    await publish_return_agreement(session)
    after = (await client.get(f"/api/v1/returns/eligibility/{seed.order_id}")).json()
    assert after["agreement_version"] == 1


async def test_another_customers_order_is_forbidden(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, email_suffix="owner")
    other = await seed_delivered_order(session, email_suffix="thief")
    as_customer(other.customer_user)

    resp = await client.get(f"/api/v1/returns/eligibility/{seed.order_id}")
    assert resp.status_code == 403


async def test_missing_order_is_404(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    as_customer(seed.customer_user)
    resp = await client.get("/api/v1/returns/eligibility/99999")
    assert resp.status_code == 404
