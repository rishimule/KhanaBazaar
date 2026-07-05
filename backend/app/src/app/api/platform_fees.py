# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Admin platform-fee configuration.

`admin_router` mounted at /api/v1/admin. Global settings + per-service fee config
+ subscription-plan pricing."""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_admin
from app.db.session import get_db_session
from app.models.base import User
from app.models.catalog import Service
from app.models.platform_fee import (
    PlatformFeeSettings,
    ServiceFeeConfig,
    ServiceSubscriptionPlan,
)
from app.schemas.platform_fees import (
    PlatformFeeSettingsPatch,
    PlatformFeeSettingsRead,
    ServiceFeeConfigPatch,
    ServiceFeeConfigRead,
    ServiceFeeConfigWithPlans,
    SubscriptionPlanItem,
    SubscriptionPlansPut,
)
from app.services import platform_fees as fees

admin_router = APIRouter()


def _settings_read(s: PlatformFeeSettings) -> PlatformFeeSettingsRead:
    return PlatformFeeSettingsRead(
        grace_period_days=s.grace_period_days,
        expiry_reminder_start_days=s.expiry_reminder_start_days,
        pending_payment_protect_days=s.pending_payment_protect_days,
        bank_account_name=s.bank_account_name,
        bank_account_number=s.bank_account_number,
        bank_ifsc=s.bank_ifsc,
        upi_id=s.upi_id,
        qr_image_url=s.qr_image_url,
        gstin=s.gstin,
    )


@admin_router.get("/fees/settings", response_model=PlatformFeeSettingsRead)
async def get_fee_settings(
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformFeeSettingsRead:
    return _settings_read(await fees.load_settings(session))


@admin_router.patch("/fees/settings", response_model=PlatformFeeSettingsRead)
async def patch_fee_settings(
    body: PlatformFeeSettingsPatch,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformFeeSettingsRead:
    row = await fees.get_or_create_settings(session)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _settings_read(row)


def _config_read(c: ServiceFeeConfig) -> ServiceFeeConfigRead:
    return ServiceFeeConfigRead(
        service_id=c.service_id,
        freebie_enabled=c.freebie_enabled,
        freebie_default_days=c.freebie_default_days,
        subscription_enabled=c.subscription_enabled,
        order_value_enabled=c.order_value_enabled,
        order_value_percent=c.order_value_percent,
        order_value_min_deposit=c.order_value_min_deposit,
        order_value_billing_day=c.order_value_billing_day,
        pay_per_txn_enabled=c.pay_per_txn_enabled,
        pay_per_txn_fee=c.pay_per_txn_fee,
        pay_per_txn_min_deposit=c.pay_per_txn_min_deposit,
        pay_per_txn_low_balance_threshold=c.pay_per_txn_low_balance_threshold,
    )


async def _require_service(session: AsyncSession, service_id: int) -> Service:
    svc = await session.get(Service, service_id)
    if svc is None:
        raise HTTPException(status_code=404, detail={"error": "service_not_found"})
    return svc


@admin_router.get("/fees/services/{service_id}", response_model=ServiceFeeConfigWithPlans)
async def get_service_fee_config(
    service_id: int,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ServiceFeeConfigWithPlans:
    await _require_service(session, service_id)
    cfg = await fees.load_service_config(session, service_id)
    plans = await fees.list_plans(session, service_id)
    return ServiceFeeConfigWithPlans(
        config=_config_read(cfg),
        plans=[
            SubscriptionPlanItem(
                duration_months=p.duration_months, price=p.price, is_active=p.is_active
            )
            for p in plans
        ],
    )


@admin_router.patch("/fees/services/{service_id}", response_model=ServiceFeeConfigRead)
async def patch_service_fee_config(
    service_id: int,
    body: ServiceFeeConfigPatch,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ServiceFeeConfigRead:
    await _require_service(session, service_id)
    cfg = await fees.get_or_create_service_config(session, service_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(cfg, key, value)
    session.add(cfg)
    await session.commit()
    await session.refresh(cfg)
    return _config_read(cfg)


@admin_router.put(
    "/fees/services/{service_id}/plans", response_model=list[SubscriptionPlanItem]
)
async def put_service_plans(
    service_id: int,
    body: SubscriptionPlansPut,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[SubscriptionPlanItem]:
    await _require_service(session, service_id)
    for item in body.plans:
        if item.duration_months not in fees.ALLOWED_DURATIONS:
            raise HTTPException(
                status_code=422,
                detail={"error": "invalid_duration", "duration_months": item.duration_months},
            )
    existing = {p.duration_months: p for p in await fees.list_plans(session, service_id)}
    seen: set[int] = set()
    for item in body.plans:
        seen.add(item.duration_months)
        row = existing.get(item.duration_months)
        if row is None:
            session.add(
                ServiceSubscriptionPlan(
                    service_id=service_id,
                    duration_months=item.duration_months,
                    price=item.price,
                    is_active=item.is_active,
                )
            )
        else:
            row.price = item.price
            row.is_active = item.is_active
            session.add(row)
    for duration, row in existing.items():
        if duration not in seen:
            await session.delete(row)
    await session.commit()
    plans = await fees.list_plans(session, service_id)
    return [
        SubscriptionPlanItem(
            duration_months=p.duration_months, price=p.price, is_active=p.is_active
        )
        for p in plans
    ]
