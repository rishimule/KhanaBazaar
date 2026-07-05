# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date, timedelta

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.platform_fee import ArrangementStatus, FeeArrangement, FeeModel
from app.services.fee_lifecycle import (
    admin_comp_subscription,
    admin_extend,
    admin_terminate,
)


async def _arr(session, bundle, *, model=FeeModel.Freebie, status=ArrangementStatus.Trial, valid_until=date(2026, 8, 1)):
    arr = FeeArrangement(
        store_id=bundle.store.id, service_id=bundle.service_id,
        model=model, status=status, valid_until=valid_until,
    )
    session.add(arr)
    await session.flush()
    return arr


@pytest.mark.asyncio
async def test_admin_extend(session: AsyncSession, approved_seller_with_store) -> None:
    arr = await _arr(session, approved_seller_with_store, valid_until=date(2026, 8, 1))
    admin_extend(session, arr, 15, admin_user_id=1)
    await session.flush()
    assert arr.valid_until == date(2026, 8, 16)


@pytest.mark.asyncio
async def test_admin_extend_from_none_uses_today(session: AsyncSession, approved_seller_with_store) -> None:
    arr = await _arr(session, approved_seller_with_store, valid_until=None)
    admin_extend(session, arr, 10, admin_user_id=1)
    await session.flush()
    assert arr.valid_until == date.today() + timedelta(days=10)


@pytest.mark.asyncio
async def test_admin_terminate(session: AsyncSession, approved_seller_with_store) -> None:
    arr = await _arr(session, approved_seller_with_store, model=FeeModel.Subscription, status=ArrangementStatus.Active)
    admin_terminate(session, arr, "policy violation", admin_user_id=1)
    await session.flush()
    assert arr.status == ArrangementStatus.Suspended
    assert arr.suspended_reason == "policy violation"
    assert arr.auto_renew is False


@pytest.mark.asyncio
async def test_admin_comp_subscription(session: AsyncSession, approved_seller_with_store) -> None:
    arr = await _arr(session, approved_seller_with_store, status=ArrangementStatus.Suspended, valid_until=date(2026, 7, 1))
    admin_comp_subscription(session, arr, 6, admin_user_id=1, today=date(2026, 7, 5))
    await session.flush()
    assert arr.model == FeeModel.Subscription
    assert arr.status == ArrangementStatus.Active
    assert arr.subscription_duration_months == 6
    assert arr.price_snapshot == 0.0
    assert arr.valid_until == date(2026, 7, 5) + timedelta(days=180)
    assert arr.suspended_at is None
