# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date, timedelta

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeModel,
    ServiceFeeConfig,
)
from app.services.fee_lifecycle import DEFAULT_FREEBIE_DAYS, sync_store_arrangements


@pytest.mark.asyncio
async def test_sync_enrolls_offered_service_into_freebie_trial(
    session: AsyncSession, approved_seller_with_store
) -> None:
    profile_id = approved_seller_with_store.profile.id
    await sync_store_arrangements(session, profile_id, today=date(2026, 7, 5))
    await session.commit()
    arr = (
        await session.exec(
            select(FeeArrangement).where(
                FeeArrangement.store_id == approved_seller_with_store.store.id
            )
        )
    ).one()
    assert arr.service_id == approved_seller_with_store.service_id
    assert arr.model == FeeModel.Freebie
    assert arr.status == ArrangementStatus.Trial
    assert arr.valid_until == date(2026, 7, 5) + timedelta(days=DEFAULT_FREEBIE_DAYS)


@pytest.mark.asyncio
async def test_sync_uses_service_config_freebie_days(
    session: AsyncSession, approved_seller_with_store
) -> None:
    session.add(
        ServiceFeeConfig(
            service_id=approved_seller_with_store.service_id, freebie_default_days=45
        )
    )
    await session.flush()
    await sync_store_arrangements(
        session, approved_seller_with_store.profile.id, today=date(2026, 7, 5)
    )
    await session.commit()
    arr = (
        await session.exec(
            select(FeeArrangement).where(
                FeeArrangement.store_id == approved_seller_with_store.store.id
            )
        )
    ).one()
    assert arr.valid_until == date(2026, 8, 19)  # 2026-07-05 + 45d


@pytest.mark.asyncio
async def test_sync_is_idempotent(
    session: AsyncSession, approved_seller_with_store
) -> None:
    pid = approved_seller_with_store.profile.id
    await sync_store_arrangements(session, pid, today=date(2026, 7, 5))
    await session.commit()
    await sync_store_arrangements(session, pid, today=date(2026, 7, 10))
    await session.commit()
    arrs = (
        await session.exec(
            select(FeeArrangement).where(
                FeeArrangement.store_id == approved_seller_with_store.store.id
            )
        )
    ).all()
    assert len(arrs) == 1  # not duplicated; valid_until keeps the original
    assert arrs[0].valid_until == date(2026, 7, 5) + timedelta(days=DEFAULT_FREEBIE_DAYS)


@pytest.mark.asyncio
async def test_sync_noop_without_store(session: AsyncSession, approved_seller) -> None:
    # approved_seller has a profile but no Store — pre-approval-style state.
    await sync_store_arrangements(session, approved_seller["profile"].id)
    await session.commit()
    count = len((await session.exec(select(FeeArrangement))).all())
    assert count == 0
