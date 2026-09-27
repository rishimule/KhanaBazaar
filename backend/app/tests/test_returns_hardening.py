# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Payment-deadline edge cases that only surface in deployment or under load."""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import Settings
from app.models.notification import Notification
from app.models.returns import (
    ReturnInitiator,
    ReturnReasonCode,
    ReturnRequest,
    ReturnRequestItem,
    ReturnSettlementChoice,
    ReturnStatus,
)
from app.services.returns import close_lapsed_payments
from tests._returns_helpers import (
    SeededOrder,
    as_customer,
    clear_overrides,
    pk,
    seed_delivered_order,
)
from tests.conftest import test_engine


@pytest.fixture(autouse=True)
def _cleanup() -> Any:
    yield
    clear_overrides()


async def _parked(
    session: AsyncSession,
    seed: SeededOrder,
    *,
    deadline: Optional[timedelta],
    decided_ago: Optional[timedelta],
) -> ReturnRequest:
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
        decided_at=None if decided_ago is None else now - decided_ago,
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


# ─── Deploy window: accepted by the API that predates the column ─────────
# The migration runs before the new API rolls out, so for a few minutes the
# old API can park cash returns without stamping a deadline. Those must not
# become the never-closing returns this whole change exists to prevent.


async def test_unstamped_return_lapses_from_its_decision_time(
    session: AsyncSession,
) -> None:
    seed = await seed_delivered_order(session)
    req = await _parked(session, seed, deadline=None, decided_ago=timedelta(days=8))
    assert req.decided_at is not None
    decided_at = req.decided_at

    assert await close_lapsed_payments(session) == [pk(req.id)]
    await session.commit()

    row = await _reload(session, pk(req.id))
    assert row.status == ReturnStatus.closed
    assert row.closed_by_user_id is None
    # Stamped on the way out, so the record states the deadline it was judged by.
    assert row.payment_confirm_expires_at == decided_at + timedelta(days=7)


async def test_unstamped_return_inside_its_window_waits(
    session: AsyncSession,
) -> None:
    seed = await seed_delivered_order(session)
    req = await _parked(session, seed, deadline=None, decided_ago=timedelta(days=2))

    assert await close_lapsed_payments(session) == []
    await session.commit()

    row = await _reload(session, pk(req.id))
    assert row.status == ReturnStatus.awaiting_payment_confirmation


async def test_return_with_no_deadline_and_no_decision_is_left_alone(
    session: AsyncSession,
) -> None:
    """Nothing to judge it by — an admin force-close is the way out."""
    seed = await seed_delivered_order(session)
    req = await _parked(session, seed, deadline=None, decided_ago=None)

    assert await close_lapsed_payments(session) == []
    await session.commit()

    row = await _reload(session, pk(req.id))
    assert row.status == ReturnStatus.awaiting_payment_confirmation


async def test_unstamped_return_reads_with_its_effective_deadline(
    session: AsyncSession, client: AsyncClient
) -> None:
    """The UI shows the date the sweep will actually use, not nothing."""
    seed = await seed_delivered_order(session)
    req = await _parked(session, seed, deadline=None, decided_ago=timedelta(days=2))
    assert req.decided_at is not None
    as_customer(seed.customer_user)

    body = (await client.get(f"/api/v1/returns/{pk(req.id)}")).json()

    assert body["payment_confirm_expires_at"] is not None
    shown = datetime.fromisoformat(body["payment_confirm_expires_at"])
    assert shown == req.decided_at + timedelta(days=7)


# ─── The sweep: one stage failing must not undo the other ────────────────


async def test_lapse_stage_failure_does_not_undo_expiry(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.services.return_comms as return_comms
    import app.services.returns as returns_svc
    from app.worker import sweep_expired_returns

    sent: list[tuple[int, str]] = []
    monkeypatch.setattr(
        return_comms, "dispatch_return_status",
        lambda return_id, event_key: sent.append((return_id, event_key)),
    )

    async def _broken(*_args: Any, **_kwargs: Any) -> list[int]:
        raise RuntimeError("lapse stage down")

    monkeypatch.setattr(returns_svc, "close_lapsed_payments", _broken)
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

    # The task still fails loudly, so the broken stage shows up in the logs…
    with pytest.raises(RuntimeError, match="lapse stage down"):
        sweep_expired_returns()

    # …but the expiry it had already done stays done, and was announced.
    row = await _reload(session, pk(unconfirmed.id))
    assert row.status == ReturnStatus.expired
    assert sent == [(pk(unconfirmed.id), "return_expired")]


async def test_sweep_skips_a_return_someone_holds_locked(
    session: AsyncSession,
) -> None:
    """A customer confirming payment right now holds the row; the sweep must
    step around it rather than close it out from under them — or block."""
    seed = await seed_delivered_order(session)
    req = await _parked(
        session, seed, deadline=timedelta(hours=-1), decided_ago=timedelta(days=8)
    )

    async with AsyncSession(test_engine) as holder:
        await holder.exec(
            select(ReturnRequest)
            .where(ReturnRequest.id == pk(req.id))
            .with_for_update()
        )
        async with AsyncSession(test_engine) as sweeper:
            # Turns "blocked on the lock" into a failure instead of a hang.
            await sweeper.execute(text("SET LOCAL lock_timeout = '2s'"))
            assert await close_lapsed_payments(sweeper) == []
            await sweeper.rollback()
        await holder.rollback()

    row = await _reload(session, pk(req.id))
    assert row.status == ReturnStatus.awaiting_payment_confirmation


# ─── Notifications: a seller-side problem never costs the customer's row ─


async def test_customer_notice_survives_a_missing_seller_copy(
    session: AsyncSession,
) -> None:
    from app.api.returns import _notify_return

    seed = await seed_delivered_order(session)
    req = await _parked(
        session, seed, deadline=timedelta(days=7), decided_ago=timedelta(0)
    )

    # No seller copy exists for this event.
    await _notify_return(session, req, "return_initiated", notify_seller=True)

    rows = list((await session.exec(select(Notification))).all())
    assert [n.customer_profile_id for n in rows] == [seed.customer_profile_id]
    assert all(n.seller_profile_id is None for n in rows)


# ─── Configuration ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "field",
    ["RETURN_PAYMENT_CONFIRM_DAYS", "RETURN_HANDOVER_DAYS", "RETURN_CONFIRM_HOURS"],
)
def test_return_deadlines_refuse_zero(field: str) -> None:
    """0 would make the hourly sweep close or expire every return on sight."""
    with pytest.raises(ValidationError):
        Settings(**{field: 0})  # type: ignore[arg-type]
