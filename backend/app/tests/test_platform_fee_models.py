# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date

import pytest
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeEvent,
    FeeEventType,
    FeeModel,
    FeePayment,
    FeePaymentKind,
    PlatformFeeSettings,
    ServiceFeeConfig,
    ServiceSubscriptionPlan,
)


@pytest.mark.asyncio
async def test_settings_defaults_persist(session: AsyncSession) -> None:
    s = PlatformFeeSettings()
    session.add(s)
    await session.commit()
    await session.refresh(s)
    assert s.grace_period_days == 2
    assert s.expiry_reminder_start_days == 7
    assert s.pending_payment_protect_days == 7


@pytest.mark.asyncio
async def test_service_config_and_plan(session: AsyncSession, approved_seller_with_store) -> None:
    cfg = ServiceFeeConfig(service_id=approved_seller_with_store.service_id)
    session.add(cfg)
    plan = ServiceSubscriptionPlan(
        service_id=approved_seller_with_store.service_id, duration_months=3, price=300.0
    )
    session.add(plan)
    await session.commit()
    await session.refresh(cfg)
    assert cfg.freebie_enabled is True
    assert cfg.freebie_default_days == 30
    assert cfg.subscription_enabled is False


@pytest.mark.asyncio
async def test_arrangement_stores_enum_by_value(
    session: AsyncSession, approved_seller_with_store
) -> None:
    arr = FeeArrangement(
        store_id=approved_seller_with_store.store.id,
        service_id=approved_seller_with_store.service_id,
        model=FeeModel.Freebie,
        status=ArrangementStatus.Trial,
        valid_until=date(2026, 8, 1),
    )
    session.add(arr)
    await session.commit()
    await session.refresh(arr)
    assert arr.id is not None
    session.add(FeePayment(arrangement_id=arr.id, kind=FeePaymentKind.SubscriptionFee, amount=300.0))
    session.add(FeeEvent(arrangement_id=arr.id, event_type=FeeEventType.ArrangementCreated))
    await session.commit()

    # Postgres enum labels must be the lowercase VALUES, not member names.
    raw = (await session.exec(text("SELECT status, model FROM fee_arrangement"))).first()
    assert raw == ("trial", "freebie")
    kind = (await session.exec(text("SELECT kind FROM fee_payment"))).first()
    assert kind == ("subscription_fee",)
    default_status = (await session.exec(text("SELECT status FROM fee_payment"))).first()
    assert default_status == ("pending",)
