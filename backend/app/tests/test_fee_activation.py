# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date, datetime, timezone

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeModel,
    FeePaymentStatus,
    ServiceFeeConfig,
    ServiceSubscriptionPlan,
)
from app.services.fee_lifecycle import (
    FeeError,
    confirm_subscription_payment,
    opt_into_subscription,
    reject_payment,
    request_cancellation,
)


async def _setup(session, bundle, *, status=ArrangementStatus.Trial, valid_until=date(2026, 8, 1)):
    session.add(ServiceFeeConfig(service_id=bundle.service_id, subscription_enabled=True))
    session.add(ServiceSubscriptionPlan(
        service_id=bundle.service_id, duration_months=3, price=300.0, is_active=True
    ))
    arr = FeeArrangement(
        store_id=bundle.store.id, service_id=bundle.service_id,
        model=FeeModel.Freebie, status=status, valid_until=valid_until,
    )
    session.add(arr)
    await session.flush()
    return arr


@pytest.mark.asyncio
async def test_opt_in_creates_pending_payment(session: AsyncSession, approved_seller_with_store) -> None:
    arr = await _setup(session, approved_seller_with_store)
    now = datetime(2026, 7, 5, tzinfo=timezone.utc)
    payment = await opt_into_subscription(session, arr, 3, now=now)
    assert payment.status == FeePaymentStatus.Pending
    assert payment.amount == 300.0
    await session.refresh(arr)
    assert arr.pending_since == now
    assert arr.queued_duration_months == 3
    # Status/model unchanged at opt-in.
    assert arr.status == ArrangementStatus.Trial
    assert arr.model == FeeModel.Freebie


@pytest.mark.asyncio
async def test_opt_in_rejects_when_not_offerable(session: AsyncSession, approved_seller_with_store) -> None:
    arr = FeeArrangement(
        store_id=approved_seller_with_store.store.id, service_id=approved_seller_with_store.service_id,
        model=FeeModel.Freebie, status=ArrangementStatus.Trial, valid_until=date(2026, 8, 1),
    )
    session.add(arr)
    await session.flush()
    with pytest.raises(FeeError):
        await opt_into_subscription(session, arr, 3)


@pytest.mark.asyncio
async def test_confirm_from_trial_activates_from_today(session: AsyncSession, approved_seller_with_store) -> None:
    arr = await _setup(session, approved_seller_with_store)
    payment = await opt_into_subscription(session, arr, 3, now=datetime(2026, 7, 5, tzinfo=timezone.utc))
    await confirm_subscription_payment(session, payment, admin_user_id=1, today=date(2026, 7, 5))
    await session.refresh(arr)
    await session.refresh(payment)
    assert payment.status == FeePaymentStatus.Confirmed
    assert arr.status == ArrangementStatus.Active
    assert arr.model == FeeModel.Subscription
    assert arr.subscription_duration_months == 3
    assert arr.price_snapshot == 300.0
    assert arr.valid_until == date(2026, 7, 5) + __import__("datetime").timedelta(days=90)
    assert arr.pending_since is None


@pytest.mark.asyncio
async def test_confirm_renewal_early_stacks(session: AsyncSession, approved_seller_with_store) -> None:
    arr = await _setup(
        session, approved_seller_with_store,
        status=ArrangementStatus.Active, valid_until=date(2026, 9, 1),
    )
    arr.model = FeeModel.Subscription
    await session.flush()
    payment = await opt_into_subscription(session, arr, 3, now=datetime(2026, 8, 20, tzinfo=timezone.utc))
    await confirm_subscription_payment(session, payment, admin_user_id=1, today=date(2026, 8, 20))
    await session.refresh(arr)
    # Renewed early → stacks onto the existing expiry, not today.
    assert arr.valid_until == date(2026, 9, 1) + __import__("datetime").timedelta(days=90)


@pytest.mark.asyncio
async def test_reject_clears_pending_leaves_arrangement(session: AsyncSession, approved_seller_with_store) -> None:
    arr = await _setup(session, approved_seller_with_store)
    payment = await opt_into_subscription(session, arr, 3, now=datetime(2026, 7, 5, tzinfo=timezone.utc))
    await reject_payment(session, payment, admin_user_id=1, reason="not received")
    await session.refresh(arr)
    await session.refresh(payment)
    assert payment.status == FeePaymentStatus.Rejected
    assert payment.reject_reason == "not received"
    assert arr.pending_since is None
    assert arr.status == ArrangementStatus.Trial  # unchanged
    assert arr.model == FeeModel.Freebie


@pytest.mark.asyncio
async def test_cancel_sets_flags(session: AsyncSession, approved_seller_with_store) -> None:
    arr = await _setup(
        session, approved_seller_with_store,
        status=ArrangementStatus.Active, valid_until=date(2026, 9, 1),
    )
    arr.model = FeeModel.Subscription
    await session.flush()
    request_cancellation(session, arr)
    await session.flush()
    await session.refresh(arr)
    assert arr.cancel_requested is True
    assert arr.auto_renew is False
