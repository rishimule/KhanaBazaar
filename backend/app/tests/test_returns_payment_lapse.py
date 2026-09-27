# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""The third swept stage: a cash return whose payment is never confirmed."""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytest
from httpx import AsyncClient
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.otp import hash_code
from app.core.redis import get_redis
from app.models.notification import Notification, NotificationType
from app.models.returns import (
    ReturnEvent,
    ReturnInitiator,
    ReturnReasonCode,
    ReturnRequest,
    ReturnRequestItem,
    ReturnSettlementChoice,
    ReturnStatus,
)
from app.services.account_lifecycle import has_open_obligations
from app.services.returns import (
    close_lapsed_payments,
    expire_stale_returns,
    locked_order_item_ids,
)
from tests._returns_helpers import (
    SeededOrder,
    as_customer,
    clear_overrides,
    pk,
    seed_delivered_order,
)


@pytest.fixture(autouse=True)
def _cleanup() -> Any:
    yield
    clear_overrides()


async def _parked(
    session: AsyncSession, seed: SeededOrder, *, deadline: Optional[timedelta]
) -> ReturnRequest:
    """A cash return the seller accepted eight days ago, awaiting the customer."""
    now = datetime.now(timezone.utc)
    req = ReturnRequest(
        order_id=seed.order_id, customer_profile_id=seed.customer_profile_id,
        store_id=seed.store_id, seller_profile_id=seed.seller_profile_id,
        service_id=seed.service_id, initiated_by=ReturnInitiator.customer,
        initiated_by_user_id=seed.customer_user_id,
        status=ReturnStatus.awaiting_payment_confirmation, is_full_order=False,
        reason_code=ReturnReasonCode.damaged, items_amount=250.0,
        delivery_fee_amount=0.0, total_amount=250.0,
        settlement_choice=ReturnSettlementChoice.payment, payment_amount=250.0,
        agreement_policy_version=1, window_expires_at=now + timedelta(days=5),
        confirm_expires_at=now - timedelta(days=9),
        decided_at=now - timedelta(days=8), decided_by_user_id=seed.seller_user_id,
        payment_confirm_expires_at=None if deadline is None else now + deadline,
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


async def _reload(session: AsyncSession, return_id: int) -> ReturnRequest:
    session.expunge_all()
    row = await session.get(ReturnRequest, return_id)
    assert row is not None
    return row


async def test_lapsed_cash_return_closes_as_system(session: AsyncSession) -> None:
    seed = await seed_delivered_order(session)
    req = await _parked(session, seed, deadline=timedelta(hours=-1))

    closed = await close_lapsed_payments(session)
    await session.commit()

    assert closed == [pk(req.id)]
    row = await _reload(session, pk(req.id))
    assert row.status == ReturnStatus.closed
    assert row.closed_by_user_id is None
    assert row.closed_at is not None
    events = (await session.exec(
        select(ReturnEvent)
        .where(ReturnEvent.return_request_id == pk(req.id))
        .order_by(col(ReturnEvent.id))
    )).all()
    assert events[-1].from_status == ReturnStatus.awaiting_payment_confirmation
    assert events[-1].to_status == ReturnStatus.closed
    assert events[-1].actor_role == "system"
    assert events[-1].actor_user_id is None
    assert events[-1].note == "payment confirmation lapsed"


async def test_lapse_notifies_customer_and_seller(session: AsyncSession) -> None:
    seed = await seed_delivered_order(session)
    req = await _parked(session, seed, deadline=timedelta(hours=-1))

    await close_lapsed_payments(session)
    await session.commit()

    rows = list((await session.exec(select(Notification))).all())
    customer = [n for n in rows if n.customer_profile_id is not None]
    seller = [n for n in rows if n.seller_profile_id is not None]
    assert len(customer) == 1 and len(seller) == 1
    assert customer[0].type == NotificationType.ReturnStatusUpdate
    assert customer[0].status_value == "closed"
    assert customer[0].return_request_id == pk(req.id)
    assert "contact support" in customer[0].body
    assert "₹250.00" in customer[0].body
    assert seller[0].type == NotificationType.SellerReturnRequest
    assert seller[0].status_value == "closed"
    assert seller[0].return_request_id == pk(req.id)


async def test_future_deadline_is_untouched(session: AsyncSession) -> None:
    """A missing deadline has its own rules — tests/test_returns_hardening.py."""
    seed = await seed_delivered_order(session)
    pending = await _parked(session, seed, deadline=timedelta(days=1))

    assert await close_lapsed_payments(session) == []
    await session.commit()

    row = await _reload(session, pk(pending.id))
    assert row.status == ReturnStatus.awaiting_payment_confirmation


async def test_lapse_keeps_the_item_lines_locked(session: AsyncSession) -> None:
    """The goods came back, so the lines must never be returnable again."""
    seed = await seed_delivered_order(session)
    await _parked(session, seed, deadline=timedelta(hours=-1))
    locked = {seed.order_item_ids[0]}
    assert await locked_order_item_ids(session, seed.order_id) == locked

    await close_lapsed_payments(session)
    await session.commit()

    assert await locked_order_item_ids(session, seed.order_id) == locked


async def test_lapse_clears_the_account_obligation(session: AsyncSession) -> None:
    seed = await seed_delivered_order(session)
    await _parked(session, seed, deadline=timedelta(hours=-1))
    assert (await has_open_obligations(session, seed.customer_profile_id))[2] == 1

    await close_lapsed_payments(session)
    await session.commit()

    assert (await has_open_obligations(session, seed.customer_profile_id))[2] == 0


async def test_expiry_sweep_leaves_parked_cash_returns_alone(
    session: AsyncSession,
) -> None:
    """Only the lapse sweep may close a parked return — never as `expired`."""
    seed = await seed_delivered_order(session)
    req = await _parked(session, seed, deadline=timedelta(hours=-1))

    assert await expire_stale_returns(session) == []
    await session.commit()

    row = await _reload(session, pk(req.id))
    assert row.status == ReturnStatus.awaiting_payment_confirmation


async def test_late_confirmation_still_closes_normally(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Past the deadline but before the sweep ran: a real confirmation wins."""
    seed = await seed_delivered_order(session)
    req = await _parked(session, seed, deadline=timedelta(minutes=-5))
    redis = await get_redis()
    await redis.hset(  # type: ignore[misc]
        f"otp:return_payment:code:{seed.customer_user_id}:{pk(req.id)}",
        mapping={"code_hash": hash_code("424242"), "attempts": "0"},
    )
    as_customer(seed.customer_user)

    resp = await client.post(
        f"/api/v1/returns/{pk(req.id)}/payment/confirm", json={"otp": "424242"}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "closed"
    assert resp.json()["payment_lapsed"] is False


async def test_lapsed_return_reads_as_lapsed(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _parked(session, seed, deadline=timedelta(hours=-1))
    await close_lapsed_payments(session)
    await session.commit()
    as_customer(seed.customer_user)

    body = (await client.get(f"/api/v1/returns/{pk(req.id)}")).json()

    assert body["status"] == "closed"
    assert body["payment_lapsed"] is True
    assert body["payment_confirm_expires_at"] is not None


async def test_sweep_task_dispatches_expiry_and_lapse(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.services.return_comms as return_comms
    from app.worker import sweep_expired_returns

    sent: list[tuple[int, str]] = []
    monkeypatch.setattr(
        return_comms, "dispatch_return_status",
        lambda return_id, event_key: sent.append((return_id, event_key)),
    )
    seed = await seed_delivered_order(session)
    now = datetime.now(timezone.utc)
    unconfirmed = ReturnRequest(
        order_id=seed.order_id, customer_profile_id=seed.customer_profile_id,
        store_id=seed.store_id, seller_profile_id=seed.seller_profile_id,
        service_id=seed.service_id, initiated_by=ReturnInitiator.customer,
        initiated_by_user_id=seed.customer_user_id,
        status=ReturnStatus.awaiting_customer_confirmation, is_full_order=False,
        reason_code=ReturnReasonCode.damaged, items_amount=300.0,
        delivery_fee_amount=0.0, total_amount=300.0,
        settlement_choice=ReturnSettlementChoice.store_credit,
        agreement_policy_version=1, window_expires_at=now + timedelta(days=5),
        confirm_expires_at=now - timedelta(hours=1),
    )
    session.add(unconfirmed)
    await session.commit()
    await session.refresh(unconfirmed)
    lapsed = await _parked(session, seed, deadline=timedelta(hours=-1))

    moved = sweep_expired_returns()

    assert moved == 2
    assert set(sent) == {
        (pk(unconfirmed.id), "return_expired"),
        (pk(lapsed.id), "return_payment_lapsed"),
    }
