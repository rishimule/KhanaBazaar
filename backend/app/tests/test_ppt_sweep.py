# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Pay-Per-Transaction daily sweep: Active→Grace (config-driven underfunding),
low-balance reminder, Grace→Suspend after the grace window."""
from datetime import date

import pytest
import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeModel,
    ServiceFeeConfig,
)
from app.services import fee_lifecycle as fl


@pytest_asyncio.fixture
async def seeded_store_with_service(approved_seller_with_store):
    bundle = approved_seller_with_store
    return bundle.store, bundle.service_id


async def _cfg(session: AsyncSession, service_id: int, *, fee=2.0, low=10.0) -> None:
    session.add(
        ServiceFeeConfig(
            service_id=service_id, pay_per_txn_enabled=True, pay_per_txn_fee=fee,
            pay_per_txn_low_balance_threshold=low,
        )
    )
    await session.flush()


async def _arr(session, store, service_id, *, status, balance, valid_until=None):
    arr = FeeArrangement(
        store_id=store.id, service_id=service_id, model=FeeModel.PayPerTransaction,
        status=status, balance=balance, valid_until=valid_until,
    )
    session.add(arr)
    await session.flush()
    return arr


@pytest.mark.asyncio
async def test_sweep_active_underfunded_to_grace(session, seeded_store_with_service):
    store, service_id = seeded_store_with_service
    await _cfg(session, service_id, fee=5.0)
    arr = await _arr(session, store, service_id, status=ArrangementStatus.Active, balance=3.0)
    await fl.run_fee_sweep(session, today=date(2026, 7, 21))
    await session.commit()
    await session.refresh(arr)
    assert arr.status == ArrangementStatus.Grace
    assert arr.valid_until == date(2026, 7, 21)


@pytest.mark.asyncio
async def test_sweep_grace_elapsed_to_suspended(session, seeded_store_with_service):
    store, service_id = seeded_store_with_service
    await _cfg(session, service_id, fee=2.0)
    arr = await _arr(session, store, service_id, status=ArrangementStatus.Grace, balance=-4.0, valid_until=date(2026, 7, 1))
    await fl.run_fee_sweep(session, today=date(2026, 7, 21))
    await session.commit()
    await session.refresh(arr)
    assert arr.status == ArrangementStatus.Suspended


@pytest.mark.asyncio
async def test_sweep_grace_within_window_stays(session, seeded_store_with_service):
    store, service_id = seeded_store_with_service
    await _cfg(session, service_id, fee=2.0)
    arr = await _arr(session, store, service_id, status=ArrangementStatus.Grace, balance=-1.0, valid_until=date(2026, 7, 21))
    await fl.run_fee_sweep(session, today=date(2026, 7, 22))  # 1 day into a 2-day grace
    await session.commit()
    await session.refresh(arr)
    assert arr.status == ArrangementStatus.Grace
