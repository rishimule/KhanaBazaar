# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""GET /orders/{id}/receipt (spec 2026-10-10 §5.1)."""
from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_user
from app.models.base import User
from app.models.commerce import Payment
from app.models.receipt import OrderReceipt
from app.models.returns import (
    ReturnInitiator,
    ReturnReasonCode,
    ReturnRequest,
    ReturnSettlementChoice,
    ReturnStatus,
)
from tests.test_orders import (  # noqa: F401
    _deliver_with_otp,
    _order_id_for_store,
    _place_orders,
    as_customer,
    mock_admin,
    mock_customer,
    mock_other_customer,
    mock_other_seller,
    mock_seller,
    seed,
)


async def _delivered_store_a_order(seed: dict[str, int]) -> int:
    order_ids = await _place_orders(seed)
    target = await _order_id_for_store(order_ids, seed["store_a"])
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        assert (await _deliver_with_otp(ac, target)).status_code == 200
    return target


async def _get(user: User, order_id: int) -> Any:
    app.dependency_overrides[get_current_user] = lambda: user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return await ac.get(f"/api/v1/orders/{order_id}/receipt")


@pytest.mark.parametrize(
    "user,expected",
    [
        (mock_customer, 200),
        (mock_other_customer, 403),
        (mock_seller, 200),
        (mock_other_seller, 403),
        (mock_admin, 200),
    ],
)
async def test_access_matches_the_order(
    as_customer: Any, seed: dict[str, int], user: User, expected: int
) -> None:
    target = await _delivered_store_a_order(seed)
    resp = await _get(user, target)
    assert resp.status_code == expected, resp.text
    if expected == 200:
        body = resp.json()
        assert body["order_id"] == target
        assert body["number"].startswith("RC-")
        assert body["issued_via"] == "delivery"
        assert body["snapshot"]["seller"]["store_name"] == "Store A"
        assert body["later_changes"] == {"refunded_at": None, "returns": []}


async def test_undelivered_order_has_no_receipt_yet(as_customer: Any, seed: dict[str, int]) -> None:
    order_ids = await _place_orders(seed)
    resp = await _get(mock_customer, order_ids[0])
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "order_not_delivered"


async def test_delivered_without_receipt_is_404(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    target = await _delivered_store_a_order(seed)
    await session.execute(delete(OrderReceipt).where(OrderReceipt.order_id == target))  # type: ignore[arg-type]
    await session.commit()
    resp = await _get(mock_customer, target)
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "receipt_not_issued"


async def test_later_changes_list_refund_and_live_returns(
    as_customer: Any, seed: dict[str, int], session: AsyncSession
) -> None:
    target = await _delivered_store_a_order(seed)
    now = datetime.now(timezone.utc)
    payment = (await session.exec(select(Payment).where(Payment.order_id == target))).one()
    payment.refunded_at = now
    session.add(payment)

    def _return(status: ReturnStatus) -> ReturnRequest:
        return ReturnRequest(
            order_id=target,
            customer_profile_id=seed["customer_profile"],
            store_id=seed["store_a"],
            seller_profile_id=seed["seller_profile"],
            service_id=seed["grocery_service_id"],
            initiated_by=ReturnInitiator.customer,
            initiated_by_user_id=mock_customer.id,
            status=status,
            reason_code=ReturnReasonCode.damaged,
            items_amount=50.0,
            total_amount=50.0,
            settlement_choice=ReturnSettlementChoice.store_credit,
            agreement_policy_version=1,
            window_expires_at=now,
            confirm_expires_at=now,
        )

    live, withdrawn = _return(ReturnStatus.active), _return(ReturnStatus.withdrawn)
    session.add_all([live, withdrawn])
    await session.commit()

    body = (await _get(mock_customer, target)).json()
    assert body["later_changes"]["refunded_at"] is not None
    assert body["later_changes"]["returns"] == [{"id": live.id, "status": "active"}]
