# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeModel,
    ServiceFeeConfig,
)
from app.services.fee_gating import (
    is_store_premium,
    premium_store_ids,
    should_gate_reports,
    store_has_offerable_paid_model,
)


async def _arr(session, store_id, service_id, *, model, status):
    session.add(FeeArrangement(
        store_id=store_id, service_id=service_id, model=model,
        status=status, valid_until=date(2026, 12, 1),
    ))
    await session.flush()


@pytest.mark.asyncio
async def test_freebie_store_not_premium(session: AsyncSession, approved_seller_with_store) -> None:
    await _arr(session, approved_seller_with_store.store.id, approved_seller_with_store.service_id,
               model=FeeModel.Freebie, status=ArrangementStatus.Trial)
    assert await is_store_premium(session, approved_seller_with_store.store.id) is False


@pytest.mark.asyncio
async def test_active_subscription_is_premium(session: AsyncSession, approved_seller_with_store) -> None:
    await _arr(session, approved_seller_with_store.store.id, approved_seller_with_store.service_id,
               model=FeeModel.Subscription, status=ArrangementStatus.Active)
    assert await is_store_premium(session, approved_seller_with_store.store.id) is True
    assert await premium_store_ids(session, [approved_seller_with_store.store.id]) == {approved_seller_with_store.store.id}


@pytest.mark.asyncio
async def test_grace_paid_counts_as_premium(session: AsyncSession, approved_seller_with_store) -> None:
    await _arr(session, approved_seller_with_store.store.id, approved_seller_with_store.service_id,
               model=FeeModel.Subscription, status=ArrangementStatus.Grace)
    assert await is_store_premium(session, approved_seller_with_store.store.id) is True


@pytest.mark.asyncio
async def test_suspended_paid_not_premium(session: AsyncSession, approved_seller_with_store) -> None:
    await _arr(session, approved_seller_with_store.store.id, approved_seller_with_store.service_id,
               model=FeeModel.Subscription, status=ArrangementStatus.Suspended)
    assert await is_store_premium(session, approved_seller_with_store.store.id) is False


@pytest.mark.asyncio
async def test_hold_no_paid_model_not_gated(session: AsyncSession, approved_seller_with_store) -> None:
    # Freebie store, no ServiceFeeConfig paid model → NOT gated (hold).
    assert await store_has_offerable_paid_model(session, approved_seller_with_store.store.id) is False
    assert await should_gate_reports(session, approved_seller_with_store.store.id) is False


@pytest.mark.asyncio
async def test_gated_when_paid_model_offerable_and_not_premium(
    session: AsyncSession, approved_seller_with_store
) -> None:
    session.add(ServiceFeeConfig(
        service_id=approved_seller_with_store.service_id, subscription_enabled=True
    ))
    await session.flush()
    assert await store_has_offerable_paid_model(session, approved_seller_with_store.store.id) is True
    assert await should_gate_reports(session, approved_seller_with_store.store.id) is True


@pytest.mark.asyncio
async def test_premium_store_never_gated(session: AsyncSession, approved_seller_with_store) -> None:
    session.add(ServiceFeeConfig(
        service_id=approved_seller_with_store.service_id, subscription_enabled=True
    ))
    await _arr(session, approved_seller_with_store.store.id, approved_seller_with_store.service_id,
               model=FeeModel.Subscription, status=ArrangementStatus.Active)
    assert await should_gate_reports(session, approved_seller_with_store.store.id) is False
