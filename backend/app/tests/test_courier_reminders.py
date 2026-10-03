# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.celery_app import celery_app
from app.models.commerce import Order, OrderStatus, Payment, PaymentStatus
from app.models.courier import CourierQuote, OrderCourier
from app.models.notification import Notification
from app.services import courier_reminders
from app.services.courier_reminders import (
    due_reminder,
    in_send_window,
    run_courier_reminder_sweep,
)
from tests._courier_helpers import SELLER, insert_courier_order, seed_courier_world

NOW = datetime(2026, 10, 2, 6, 30, tzinfo=timezone.utc)  # 12:00 IST
OLD = NOW - timedelta(hours=25)


def _state(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "status": OrderStatus.Pending, "payment_status": PaymentStatus.Pending,
        "payment_amount": 320.0,
        "placed_at": OLD, "latest_quote_version": None, "latest_quote_at": None,
        "accepted_at": None, "claimed_at": None, "rejected_at": None,
        "rejection_count": 0, "eta_to": None, "cancelled_at": None, "now": NOW,
    }
    base.update(overrides)
    return base


def test_due_reminder_rules() -> None:
    S = OrderStatus
    assert due_reminder(**_state()).key == "pending"  # type: ignore[union-attr]
    assert due_reminder(**_state(placed_at=NOW - timedelta(hours=23))) is None
    quoted = due_reminder(**_state(status=S.Quoted, latest_quote_version=2, latest_quote_at=OLD))
    assert quoted is not None and (quoted.key, quoted.customer_event) == ("quoted:v2", "reminder_quote")
    unpaid = due_reminder(**_state(status=S.Accepted, accepted_at=OLD, rejection_count=1))
    assert unpaid is not None and unpaid.key == "accepted:r1"
    rejected_recently = due_reminder(**_state(
        status=S.Accepted, accepted_at=OLD, rejected_at=NOW - timedelta(hours=1), rejection_count=1,
    ))
    assert rejected_recently is None  # the clock restarts at the rejection
    claimed = due_reminder(**_state(status=S.Accepted, accepted_at=OLD, claimed_at=OLD))
    assert claimed is not None and (claimed.key, claimed.seller_event) == ("claimed:r0", "reminder_payment_check")
    overdue = due_reminder(**_state(status=S.Dispatched, eta_to=date(2026, 9, 29)))
    assert overdue is not None and overdue.customer_event and overdue.seller_event
    assert due_reminder(**_state(status=S.Dispatched, eta_to=date(2026, 10, 1))) is None
    refund = due_reminder(**_state(
        status=S.Cancelled, payment_status=PaymentStatus.Paid, cancelled_at=NOW - timedelta(days=4),
    ))
    assert refund is not None and refund.key == "refund:3"
    assert due_reminder(**_state(status=S.Cancelled, cancelled_at=NOW - timedelta(days=4))) is None
    # A ₹0 payment (all store credit) was handed back as credit: nothing to chase.
    assert due_reminder(**_state(
        status=S.Cancelled, payment_status=PaymentStatus.Paid, payment_amount=0.0,
        cancelled_at=NOW - timedelta(days=4),
    )) is None


def test_send_window_is_daytime_ist() -> None:
    assert not in_send_window(datetime(2026, 10, 2, 3, 29, tzinfo=timezone.utc))  # 08:59 IST
    assert in_send_window(datetime(2026, 10, 2, 3, 30, tzinfo=timezone.utc))  # 09:00
    assert in_send_window(datetime(2026, 10, 2, 15, 29, tzinfo=timezone.utc))  # 20:59
    assert not in_send_window(datetime(2026, 10, 2, 15, 30, tzinfo=timezone.utc))  # 21:00


def _at_ist_hour(hour: int) -> datetime:
    """UTC instant on 2026-10-02 that is `hour`:00 IST (UTC+5:30)."""
    return datetime(2026, 10, 2, tzinfo=timezone.utc) + timedelta(hours=hour - 5.5)


def test_send_window_handles_every_quiet_hours_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    # A quiet window that doesn't wrap midnight: quiet 00:00–06:59 only.
    monkeypatch.setattr(settings, "COURIER_QUIET_START_HOUR", 0)
    monkeypatch.setattr(settings, "COURIER_QUIET_END_HOUR", 7)
    assert not in_send_window(_at_ist_hour(0))
    assert not in_send_window(_at_ist_hour(6))
    assert in_send_window(_at_ist_hour(7))
    assert in_send_window(_at_ist_hour(23))
    # START == END: no quiet hours at all (it used to mute every reminder).
    monkeypatch.setattr(settings, "COURIER_QUIET_START_HOUR", 5)
    monkeypatch.setattr(settings, "COURIER_QUIET_END_HOUR", 5)
    assert all(in_send_window(_at_ist_hour(h)) for h in range(24))


async def _backdate_order(session: AsyncSession, order_id: int, placed_at: datetime) -> None:
    order = await session.get(Order, order_id)
    assert order is not None
    order.placed_at = placed_at
    await session.commit()


async def _reminders(session: AsyncSession, order_id: int) -> list[str]:
    rows = (await session.exec(select(Notification).where(Notification.order_id == order_id))).all()
    return [r.status_value for r in rows if r.status_value.startswith("courier_reminder")]


async def test_pending_order_reminds_the_seller_once(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await insert_courier_order(session, world)
    await _backdate_order(session, order_id, OLD)
    assert await run_courier_reminder_sweep(now=NOW) == 1
    assert await run_courier_reminder_sweep(now=NOW) == 0
    assert await _reminders(session, order_id) == ["courier_reminder_quote"]
    order = await session.get(Order, order_id)
    assert order is not None
    await session.refresh(order)
    assert order.status is OrderStatus.Pending  # reminders never change state


async def test_quiet_hours_send_nothing(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await insert_courier_order(session, world)
    await _backdate_order(session, order_id, OLD)
    night = datetime(2026, 10, 2, 17, 0, tzinfo=timezone.utc)  # 22:30 IST
    assert await run_courier_reminder_sweep(now=night) == 0


async def test_a_revised_quote_gets_its_own_reminder(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await insert_courier_order(session, world, status=OrderStatus.Quoted, quote_fee=120.0)
    first = (await session.exec(select(CourierQuote).where(CourierQuote.order_id == order_id))).one()
    first.created_at = OLD
    await session.commit()
    assert await run_courier_reminder_sweep(now=NOW) == 1
    session.add(CourierQuote(
        order_id=order_id, version=2, courier_fee=150.0, eta_min_days=3, eta_max_days=5,
        created_by_user_id=SELLER.id, created_at=OLD,
    ))
    await session.commit()
    assert await run_courier_reminder_sweep(now=NOW) == 1
    assert len(await _reminders(session, order_id)) == 2


async def test_refund_reminders_follow_the_cadence(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await insert_courier_order(
        session, world, status=OrderStatus.Cancelled, payment_status=PaymentStatus.Paid,
    )
    row = (await session.exec(select(OrderCourier).where(OrderCourier.order_id == order_id))).one()
    row.cancelled_at = NOW - timedelta(days=4)
    await session.commit()
    assert await run_courier_reminder_sweep(now=NOW) == 1
    await session.refresh(row)
    assert row.last_reminder_key == "refund:3"
    row.cancelled_at = NOW - timedelta(days=8)
    await session.commit()
    assert await run_courier_reminder_sweep(now=NOW) == 1
    await session.refresh(row)
    assert row.last_reminder_key == "refund:7"


async def test_overdue_shipment_tells_both_sides(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await insert_courier_order(
        session, world, status=OrderStatus.Dispatched, payment_status=PaymentStatus.Paid,
    )
    row = (await session.exec(select(OrderCourier).where(OrderCourier.order_id == order_id))).one()
    row.eta_to = date(2026, 9, 28)
    await session.commit()
    assert await run_courier_reminder_sweep(now=NOW) == 1
    assert sorted(await _reminders(session, order_id)) == [
        "courier_reminder_arrival", "courier_reminder_overdue",
    ]


async def test_one_failure_does_not_stop_the_rest(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = await seed_courier_world(session)
    broken = await insert_courier_order(session, world)
    healthy = await insert_courier_order(session, world)
    await _backdate_order(session, broken, OLD)
    await _backdate_order(session, healthy, OLD)
    original = courier_reminders._remind_one

    async def flaky(order_id: int, now: datetime) -> bool:
        if order_id == broken:
            raise RuntimeError("boom")
        return await original(order_id, now)

    monkeypatch.setattr(courier_reminders, "_remind_one", flaky)
    with pytest.raises(RuntimeError):
        await run_courier_reminder_sweep(now=NOW)
    assert await _reminders(session, healthy) == ["courier_reminder_quote"]


def test_beat_schedule_runs_hourly() -> None:
    entry = celery_app.conf.beat_schedule["courier-reminders-hourly"]
    assert entry["task"] == "courier.send_reminders"
    # Minute 17 UTC is :47 IST; docs/courier_delivery.md §8 states it.
    assert entry["schedule"].minute == {17}


async def test_a_row_held_by_a_live_request_is_skipped(session: AsyncSession) -> None:
    from app.services.courier_rules import lock_order
    from tests.conftest import test_engine

    world = await seed_courier_world(session)
    order_id = await insert_courier_order(session, world)
    await _backdate_order(session, order_id, OLD)
    async with AsyncSession(test_engine) as live_request:
        await lock_order(live_request, order_id)
        assert await run_courier_reminder_sweep(now=NOW) == 0
    assert await run_courier_reminder_sweep(now=NOW) == 1  # the next sweep catches it


async def test_payment_rows_are_untouched(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await insert_courier_order(session, world, status=OrderStatus.Accepted, claimed=True)
    payment = (await session.exec(select(Payment).where(Payment.order_id == order_id))).one()
    payment.customer_claimed_at = OLD
    row = (await session.exec(select(OrderCourier).where(OrderCourier.order_id == order_id))).one()
    row.accepted_at = OLD
    await session.commit()
    assert await run_courier_reminder_sweep(now=NOW) == 1
    await session.refresh(payment)
    assert payment.status is PaymentStatus.Pending and payment.customer_claimed_at is not None


async def test_no_pay_now_reminder_while_the_store_cannot_be_paid(session: AsyncSession) -> None:
    from app.models.profile import SellerProfile

    world = await seed_courier_world(session)
    order_id = await insert_courier_order(session, world, status=OrderStatus.Accepted)
    row = (await session.exec(select(OrderCourier).where(OrderCourier.order_id == order_id))).one()
    row.accepted_at = OLD
    seller = await session.get(SellerProfile, world.seller_profile_id)
    assert seller is not None
    seller.upi_enabled = False
    seller.bank_transfer_enabled = False
    await session.commit()
    assert await run_courier_reminder_sweep(now=NOW) == 0
    assert await _reminders(session, order_id) == []
    # Unstamped, so it goes out as soon as a payee is back.
    seller.upi_enabled = True
    await session.commit()
    assert await run_courier_reminder_sweep(now=NOW) == 1
    assert await _reminders(session, order_id) == ["courier_reminder_payment"]
