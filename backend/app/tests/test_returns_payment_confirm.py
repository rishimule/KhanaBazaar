# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.otp import hash_code
from app.core.redis import get_redis
from app.models.returns import (
    ReturnInitiator,
    ReturnReasonCode,
    ReturnRequest,
    ReturnSettlementChoice,
    ReturnStatus,
)
from tests._returns_helpers import as_customer, clear_overrides, seed_delivered_order


@pytest.fixture(autouse=True)
def _cleanup() -> Any:
    yield
    clear_overrides()


async def _awaiting_payment(session: AsyncSession, seed: Any) -> ReturnRequest:
    now = datetime.now(timezone.utc)
    req = ReturnRequest(
        order_id=seed.order_id, customer_profile_id=seed.customer_profile_id,
        store_id=seed.store_id, seller_profile_id=seed.seller_profile_id,
        service_id=seed.service_id, initiated_by=ReturnInitiator.customer,
        initiated_by_user_id=seed.customer_user_id,
        status=ReturnStatus.awaiting_payment_confirmation, is_full_order=False,
        reason_code=ReturnReasonCode.damaged, items_amount=250.0,
        delivery_fee_amount=0.0, total_amount=250.0, payment_amount=250.0,
        settlement_choice=ReturnSettlementChoice.payment, agreement_policy_version=1,
        window_expires_at=now + timedelta(days=5),
        confirm_expires_at=now + timedelta(hours=48), decided_at=now,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req


async def _known_code(user_id: int, return_id: int, code: str = "313131") -> None:
    redis = await get_redis()
    await redis.hset(  # type: ignore[misc]
        f"otp:return_payment:code:{user_id}:{return_id}",
        mapping={"code_hash": hash_code(code), "attempts": "0"},
    )


async def test_confirming_payment_closes_the_return(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _awaiting_payment(session, seed)
    as_customer(seed.customer_user)
    await _known_code(seed.customer_user_id, req.id)

    resp = await client.post(
        f"/api/v1/returns/{req.id}/payment/confirm", json={"otp": "313131"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "closed"

    session.expunge_all()
    row = await session.get(ReturnRequest, req.id)
    assert row is not None
    assert row.closed_at is not None


async def test_wrong_code_leaves_it_open(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _awaiting_payment(session, seed)
    as_customer(seed.customer_user)
    await _known_code(seed.customer_user_id, req.id)

    resp = await client.post(
        f"/api/v1/returns/{req.id}/payment/confirm", json={"otp": "000000"}
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "return_otp_invalid"

    session.expunge_all()
    row = await session.get(ReturnRequest, req.id)
    assert row is not None
    assert row.status == ReturnStatus.awaiting_payment_confirmation


async def test_confirming_consumes_the_code(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _awaiting_payment(session, seed)
    as_customer(seed.customer_user)
    await _known_code(seed.customer_user_id, req.id)

    await client.post(
        f"/api/v1/returns/{req.id}/payment/confirm", json={"otp": "313131"}
    )
    redis = await get_redis()
    key = f"otp:return_payment:code:{seed.customer_user_id}:{req.id}"
    assert await redis.hget(key, "code_hash") is None  # type: ignore[misc]


async def test_otp_request_stores_a_code(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _awaiting_payment(session, seed)
    as_customer(seed.customer_user)

    resp = await client.post(f"/api/v1/returns/{req.id}/payment/otp/request")
    assert resp.status_code == 200
    redis = await get_redis()
    key = f"otp:return_payment:code:{seed.customer_user_id}:{req.id}"
    assert await redis.hget(key, "code_hash") is not None  # type: ignore[misc]


async def test_otp_request_in_the_wrong_state_is_refused(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _awaiting_payment(session, seed)
    req.status = ReturnStatus.active
    session.add(req)
    await session.commit()
    as_customer(seed.customer_user)

    resp = await client.post(f"/api/v1/returns/{req.id}/payment/otp/request")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "return_not_awaiting_payment"


async def test_confirming_in_the_wrong_state_is_refused(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _awaiting_payment(session, seed)
    req.status = ReturnStatus.active
    session.add(req)
    await session.commit()
    as_customer(seed.customer_user)
    await _known_code(seed.customer_user_id, req.id)

    resp = await client.post(
        f"/api/v1/returns/{req.id}/payment/confirm", json={"otp": "313131"}
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "illegal_return_transition"


async def test_another_customer_cannot_confirm_payment(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, email_suffix="owner")
    other = await seed_delivered_order(session, email_suffix="other")
    req = await _awaiting_payment(session, seed)
    await _known_code(seed.customer_user_id, req.id)
    as_customer(other.customer_user)

    resp = await client.post(
        f"/api/v1/returns/{req.id}/payment/confirm", json={"otp": "313131"}
    )
    assert resp.status_code == 404
