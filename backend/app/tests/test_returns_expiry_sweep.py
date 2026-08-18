# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.returns import (
    ReturnEvent,
    ReturnInitiator,
    ReturnReasonCode,
    ReturnRequest,
    ReturnRequestItem,
    ReturnSettlementChoice,
    ReturnStatus,
)
from app.services.returns import expire_stale_returns, locked_order_item_ids
from tests._returns_helpers import pk, seed_delivered_order


async def _request(
    session: AsyncSession,
    seed: Any,
    *,
    status: ReturnStatus,
    confirm_delta: timedelta,
    handover_delta: Optional[timedelta],
) -> ReturnRequest:
    now = datetime.now(timezone.utc)
    req = ReturnRequest(
        order_id=seed.order_id, customer_profile_id=seed.customer_profile_id,
        store_id=seed.store_id, seller_profile_id=seed.seller_profile_id,
        service_id=seed.service_id, initiated_by=ReturnInitiator.customer,
        initiated_by_user_id=seed.customer_user_id, status=status,
        is_full_order=False, reason_code=ReturnReasonCode.damaged,
        items_amount=100.0, delivery_fee_amount=0.0, total_amount=100.0,
        settlement_choice=ReturnSettlementChoice.store_credit,
        agreement_policy_version=1, window_expires_at=now + timedelta(days=5),
        confirm_expires_at=now + confirm_delta,
        handover_expires_at=None if handover_delta is None else now + handover_delta,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req


async def test_unconfirmed_return_past_its_deadline_expires(
    session: AsyncSession,
) -> None:
    seed = await seed_delivered_order(session)
    req = await _request(
        session, seed, status=ReturnStatus.awaiting_customer_confirmation,
        confirm_delta=timedelta(hours=-1), handover_delta=None,
    )
    expired = await expire_stale_returns(session)
    await session.commit()

    assert expired == [pk(req.id)]
    session.expunge_all()
    row = await session.get(ReturnRequest, pk(req.id))
    assert row is not None
    assert row.status == ReturnStatus.expired

    events = (await session.exec(
        select(ReturnEvent).where(ReturnEvent.return_request_id == pk(req.id))
    )).all()
    assert events[-1].actor_role == "system"
    assert events[-1].actor_user_id is None
    assert events[-1].note == "expired by sweep"


async def test_active_return_past_handover_expires_and_clears_the_code(
    session: AsyncSession,
) -> None:
    seed = await seed_delivered_order(session)
    req = await _request(
        session, seed, status=ReturnStatus.active,
        confirm_delta=timedelta(hours=-50), handover_delta=timedelta(days=-1),
    )
    req.receipt_otp = "123456"
    session.add(req)
    await session.commit()

    await expire_stale_returns(session)
    await session.commit()

    session.expunge_all()
    row = await session.get(ReturnRequest, pk(req.id))
    assert row is not None
    assert row.status == ReturnStatus.expired
    assert row.receipt_otp is None


async def test_returns_inside_their_deadlines_are_untouched(
    session: AsyncSession,
) -> None:
    seed = await seed_delivered_order(session)
    fresh = await _request(
        session, seed, status=ReturnStatus.awaiting_customer_confirmation,
        confirm_delta=timedelta(hours=5), handover_delta=None,
    )
    live = await _request(
        session, seed, status=ReturnStatus.active,
        confirm_delta=timedelta(hours=-50), handover_delta=timedelta(days=3),
    )
    expired = await expire_stale_returns(session)
    await session.commit()

    assert expired == []
    session.expunge_all()
    fresh_row = await session.get(ReturnRequest, pk(fresh.id))
    live_row = await session.get(ReturnRequest, pk(live.id))
    assert fresh_row is not None and live_row is not None
    assert fresh_row.status == ReturnStatus.awaiting_customer_confirmation
    assert live_row.status == ReturnStatus.active


async def test_an_active_return_is_not_judged_by_the_confirm_deadline(
    session: AsyncSession,
) -> None:
    """confirm_expires_at is long past on every active return — only
    handover_expires_at may expire it."""
    seed = await seed_delivered_order(session)
    live = await _request(
        session, seed, status=ReturnStatus.active,
        confirm_delta=timedelta(days=-30), handover_delta=timedelta(days=2),
    )
    assert await expire_stale_returns(session) == []
    await session.commit()
    session.expunge_all()
    row = await session.get(ReturnRequest, pk(live.id))
    assert row is not None
    assert row.status == ReturnStatus.active


async def test_terminal_returns_are_never_swept(session: AsyncSession) -> None:
    seed = await seed_delivered_order(session)
    closed = await _request(
        session, seed, status=ReturnStatus.closed,
        confirm_delta=timedelta(hours=-99), handover_delta=timedelta(days=-9),
    )
    expired = await expire_stale_returns(session)
    await session.commit()

    assert expired == []
    session.expunge_all()
    row = await session.get(ReturnRequest, pk(closed.id))
    assert row is not None
    assert row.status == ReturnStatus.closed


async def test_expiry_releases_the_item_lines(session: AsyncSession) -> None:
    """An expired return must not keep its lines locked forever."""
    seed = await seed_delivered_order(session)
    req = await _request(
        session, seed, status=ReturnStatus.active,
        confirm_delta=timedelta(hours=-50), handover_delta=timedelta(days=-1),
    )
    session.add(ReturnRequestItem(
        return_request_id=pk(req.id), order_item_id=seed.order_item_ids[0],
        quantity=1, product_name_snapshot="Ghee 1L", unit_price_snapshot=250.0,
        line_total=250.0,
    ))
    await session.commit()
    assert await locked_order_item_ids(session, seed.order_id) == {
        seed.order_item_ids[0]
    }

    await expire_stale_returns(session)
    await session.commit()
    assert await locked_order_item_ids(session, seed.order_id) == set()


async def test_celery_task_runs_the_sweep(session: AsyncSession) -> None:
    """The task is thread-bridged; EAGER mode must not deadlock on it."""
    from app.worker import sweep_expired_returns

    seed = await seed_delivered_order(session)
    await _request(
        session, seed, status=ReturnStatus.awaiting_customer_confirmation,
        confirm_delta=timedelta(hours=-1), handover_delta=None,
    )
    moved = sweep_expired_returns()
    assert moved == 1
