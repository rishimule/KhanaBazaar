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


@pytest.mark.asyncio
async def test_approval_enrolls_services(
    client, admin_auth_headers, pending_seller, session: AsyncSession
) -> None:
    from app.models.catalog import Service, ServiceTranslation
    from app.models.profile import SellerProfileService

    profile = pending_seller["profile"]
    svc = Service(slug="grocery-enroll", is_active=True, sort_order=0)
    session.add(svc)
    await session.flush()
    session.add(ServiceTranslation(service_id=svc.id, language_code="en", name="Grocery"))
    session.add(SellerProfileService(seller_profile_id=profile.id, service_id=svc.id))
    await session.commit()

    r = await client.patch(
        f"/api/v1/sellers/admin/{pending_seller['user'].id}/verify",
        headers=admin_auth_headers,
        json={"action": "approve"},
    )
    assert r.status_code == 200

    from app.models.platform_fee import ArrangementStatus, FeeArrangement
    from app.models.store import Store

    store = (await session.exec(select(Store).where(Store.seller_profile_id == profile.id))).one()
    arr = (await session.exec(select(FeeArrangement).where(FeeArrangement.store_id == store.id))).one()
    assert arr.service_id == svc.id
    assert arr.status == ArrangementStatus.Trial


@pytest.mark.asyncio
async def test_backfill_enrolls_existing_stores(
    session: AsyncSession, approved_seller_with_store
) -> None:
    from app.models.platform_fee import FeeArrangement
    from scripts.backfill_freebie_arrangements import backfill_all

    n = await backfill_all(session)
    await session.commit()
    assert n >= 1
    arrs = (
        await session.exec(
            select(FeeArrangement).where(
                FeeArrangement.store_id == approved_seller_with_store.store.id
            )
        )
    ).all()
    assert len(arrs) == 1


async def _make_arrangement(session, store_id, service_id, *, model, status, valid_until):
    from app.models.platform_fee import FeeArrangement

    arr = FeeArrangement(
        store_id=store_id, service_id=service_id, model=model,
        status=status, valid_until=valid_until,
    )
    session.add(arr)
    await session.flush()
    return arr


@pytest.mark.asyncio
async def test_sweep_holds_expired_freebie_when_no_paid_model(
    session: AsyncSession, approved_seller_with_store
) -> None:
    from app.models.platform_fee import ArrangementStatus, FeeModel
    from app.services.fee_lifecycle import run_fee_sweep

    arr = await _make_arrangement(
        session, approved_seller_with_store.store.id,
        approved_seller_with_store.service_id,
        model=FeeModel.Freebie, status=ArrangementStatus.Trial,
        valid_until=date(2026, 7, 1),
    )
    counts = await run_fee_sweep(session, today=date(2026, 7, 10))
    await session.refresh(arr)
    assert arr.status == ArrangementStatus.Trial  # held
    assert counts["held"] == 1


@pytest.mark.asyncio
async def test_sweep_trial_to_grace_when_paid_model_offerable(
    session: AsyncSession, approved_seller_with_store
) -> None:
    from app.models.platform_fee import ArrangementStatus, FeeModel, ServiceFeeConfig
    from app.services.fee_lifecycle import run_fee_sweep

    session.add(ServiceFeeConfig(
        service_id=approved_seller_with_store.service_id, subscription_enabled=True
    ))
    arr = await _make_arrangement(
        session, approved_seller_with_store.store.id,
        approved_seller_with_store.service_id,
        model=FeeModel.Freebie, status=ArrangementStatus.Trial,
        valid_until=date(2026, 7, 1),
    )
    counts = await run_fee_sweep(session, today=date(2026, 7, 10))
    await session.refresh(arr)
    assert arr.status == ArrangementStatus.Grace
    assert counts["to_grace"] == 1


@pytest.mark.asyncio
async def test_sweep_grace_to_suspended(
    session: AsyncSession, approved_seller_with_store
) -> None:
    from app.models.platform_fee import ArrangementStatus, FeeModel
    from app.services.fee_lifecycle import run_fee_sweep

    # default grace = 2 (no PlatformFeeSettings row). valid_until 2026-07-01,
    # grace ends 07-03; today 07-10 → suspend.
    arr = await _make_arrangement(
        session, approved_seller_with_store.store.id,
        approved_seller_with_store.service_id,
        model=FeeModel.Freebie, status=ArrangementStatus.Grace,
        valid_until=date(2026, 7, 1),
    )
    counts = await run_fee_sweep(session, today=date(2026, 7, 10))
    await session.refresh(arr)
    assert arr.status == ArrangementStatus.Suspended
    assert arr.suspended_at is not None
    assert counts["to_suspended"] == 1


@pytest.mark.asyncio
async def test_sweep_suspends_immediately_when_grace_zero(
    session: AsyncSession, approved_seller_with_store
) -> None:
    from app.models.platform_fee import (
        ArrangementStatus,
        FeeModel,
        PlatformFeeSettings,
        ServiceFeeConfig,
    )
    from app.services.fee_lifecycle import run_fee_sweep

    session.add(PlatformFeeSettings(grace_period_days=0))
    session.add(ServiceFeeConfig(
        service_id=approved_seller_with_store.service_id, subscription_enabled=True
    ))
    arr = await _make_arrangement(
        session, approved_seller_with_store.store.id,
        approved_seller_with_store.service_id,
        model=FeeModel.Freebie, status=ArrangementStatus.Trial,
        valid_until=date(2026, 7, 1),
    )
    counts = await run_fee_sweep(session, today=date(2026, 7, 10))
    await session.refresh(arr)
    assert arr.status == ArrangementStatus.Suspended
    assert counts["to_suspended"] == 1


@pytest.mark.asyncio
async def test_sweep_ignores_unexpired_and_suspended(
    session: AsyncSession, approved_seller_with_store
) -> None:
    from app.models.platform_fee import ArrangementStatus, FeeModel
    from app.services.fee_lifecycle import run_fee_sweep

    arr = await _make_arrangement(
        session, approved_seller_with_store.store.id,
        approved_seller_with_store.service_id,
        model=FeeModel.Freebie, status=ArrangementStatus.Trial,
        valid_until=date(2026, 12, 1),  # future
    )
    counts = await run_fee_sweep(session, today=date(2026, 7, 10))
    await session.refresh(arr)
    assert arr.status == ArrangementStatus.Trial
    assert counts == {
        "to_grace": 0, "to_suspended": 0, "held": 0, "protected": 0, "reminded": 0,
        "invoices_raised": 0, "ov_overdue": 0,
    }


def test_daily_sweep_task_registered_and_scheduled() -> None:
    from app.core.celery_app import celery_app

    assert "fees.run_daily_sweep" in celery_app.tasks
    sched = celery_app.conf.beat_schedule
    assert "fees-daily-sweep" in sched
    assert sched["fees-daily-sweep"]["task"] == "fees.run_daily_sweep"
