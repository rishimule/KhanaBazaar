# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Acceptance stamps a payment-confirmation deadline on cash returns only."""
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.commerce import PaymentMethod
from app.models.credit import CreditAccount
from app.models.returns import (
    ReturnInitiator,
    ReturnReasonCode,
    ReturnRequest,
    ReturnRequestItem,
    ReturnSettlementChoice,
    ReturnStatus,
)
from tests._returns_helpers import (
    SeededOrder,
    as_seller,
    clear_overrides,
    pk,
    seed_delivered_order,
)


@pytest.fixture(autouse=True)
def _cleanup() -> Any:
    yield
    clear_overrides()


async def _active(
    session: AsyncSession, seed: SeededOrder, *, choice: ReturnSettlementChoice
) -> ReturnRequest:
    now = datetime.now(timezone.utc)
    req = ReturnRequest(
        order_id=seed.order_id, customer_profile_id=seed.customer_profile_id,
        store_id=seed.store_id, seller_profile_id=seed.seller_profile_id,
        service_id=seed.service_id, initiated_by=ReturnInitiator.customer,
        initiated_by_user_id=seed.customer_user_id, status=ReturnStatus.active,
        is_full_order=False, reason_code=ReturnReasonCode.damaged,
        items_amount=250.0, delivery_fee_amount=0.0, total_amount=250.0,
        settlement_choice=choice, agreement_policy_version=1,
        window_expires_at=now + timedelta(days=5),
        confirm_expires_at=now + timedelta(hours=48),
        handover_expires_at=now + timedelta(days=7),
        receipt_otp="111222", receipt_otp_sent_at=now,
    )
    session.add(req)
    await session.flush()
    session.add(ReturnRequestItem(
        return_request_id=req.id, order_item_id=seed.order_item_ids[0],
        quantity=1, product_name_snapshot="Ghee 1L", unit_price_snapshot=250.0,
        line_total=250.0,
    ))
    await session.commit()
    await session.refresh(req)
    return req


async def _accept(client: AsyncClient, req: ReturnRequest) -> Response:
    return await client.post(
        f"/api/v1/sellers/me/returns/{pk(req.id)}/accept",
        json={"otp": "111222", "restock": False},
    )


async def test_cash_acceptance_sets_the_payment_deadline(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active(session, seed, choice=ReturnSettlementChoice.payment)
    as_seller(seed.seller_user)

    resp = await _accept(client, req)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "awaiting_payment_confirmation"
    deadline = datetime.fromisoformat(body["payment_confirm_expires_at"])
    expected = datetime.now(timezone.utc) + timedelta(
        days=settings.RETURN_PAYMENT_CONFIRM_DAYS
    )
    assert abs((deadline - expected).total_seconds()) < 120
    assert body["payment_lapsed"] is False


async def test_store_credit_acceptance_sets_no_deadline(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active(session, seed, choice=ReturnSettlementChoice.store_credit)
    as_seller(seed.seller_user)

    body = (await _accept(client, req)).json()

    assert body["status"] == "closed"
    assert body["payment_confirm_expires_at"] is None
    assert body["payment_lapsed"] is False


async def test_cash_absorbed_by_debt_reversal_sets_no_deadline(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Nothing left to hand over, so there is nothing to confirm."""
    seed = await seed_delivered_order(session, payment_method=PaymentMethod.Credit)
    session.add(CreditAccount(
        seller_profile_id=seed.seller_profile_id,
        customer_profile_id=seed.customer_profile_id,
        credit_limit=5000.0, outstanding_balance=900.0, granted_by_user_id=1,
    ))
    await session.commit()
    req = await _active(session, seed, choice=ReturnSettlementChoice.payment)
    as_seller(seed.seller_user)

    body = (await _accept(client, req)).json()

    assert body["status"] == "closed"
    assert body["credit_reversal_amount"] == 250.0
    assert body["payment_confirm_expires_at"] is None
