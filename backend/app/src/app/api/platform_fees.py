# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Admin platform-fee configuration.

`admin_router` mounted at /api/v1/admin. Global settings + per-service fee config
+ subscription-plan pricing."""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_admin, get_current_seller
from app.db.session import get_db_session
from app.models.base import User
from app.models.catalog import Service
from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeModel,
    FeePayment,
    FeePaymentStatus,
    PlatformFeeSettings,
    ServiceFeeConfig,
    ServiceSubscriptionPlan,
)
from app.models.profile import SellerProfile
from app.models.store import Store
from app.schemas.platform_fees import (
    MarkPaidBody,
    OptInBody,
    PlatformFeeSettingsPatch,
    PlatformFeeSettingsRead,
    SellerPaymentDetails,
    SellerPlanServiceView,
    SellerPlanView,
    ServiceFeeConfigPatch,
    ServiceFeeConfigRead,
    ServiceFeeConfigWithPlans,
    SubscriptionPlanItem,
    SubscriptionPlansPut,
)
from app.services import platform_fees as fees
from app.services import seller_services
from app.services.fee_lifecycle import (
    FeeError,
    opt_into_subscription,
    request_cancellation,
)

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


seller_router = APIRouter()


async def _seller_store(session: AsyncSession, user: User) -> tuple[SellerProfile, Store]:
    profile = (
        await session.exec(select(SellerProfile).where(SellerProfile.user_id == user.id))
    ).first()
    if profile is None:
        raise HTTPException(status_code=404, detail={"error": "seller_not_found"})
    store = (
        await session.exec(select(Store).where(Store.seller_profile_id == profile.id))
    ).first()
    if store is None:
        raise HTTPException(status_code=409, detail={"error": "store_not_provisioned"})
    return profile, store


async def _arrangement(session: AsyncSession, store_id: int, service_id: int) -> FeeArrangement:
    arr = (
        await session.exec(
            select(FeeArrangement).where(
                FeeArrangement.store_id == store_id,
                FeeArrangement.service_id == service_id,
            )
        )
    ).first()
    if arr is None:
        raise HTTPException(status_code=404, detail={"error": "arrangement_not_found"})
    return arr


@seller_router.get("/me/plan", response_model=SellerPlanView)
async def get_my_plan(
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> SellerPlanView:
    profile, store = await _seller_store(session, seller)
    services = await seller_services.list_profile_services(session, profile.id)
    arrangements = {
        a.service_id: a
        for a in (
            await session.exec(
                select(FeeArrangement).where(FeeArrangement.store_id == store.id)
            )
        ).all()
    }
    settings_row = await fees.load_settings(session)
    views: list[SellerPlanServiceView] = []
    for svc in services:
        cfg = await fees.load_service_config(session, svc.id)
        plans = await fees.list_plans(session, svc.id)
        arr = arrangements.get(svc.id)
        pending = arr is not None and arr.pending_since is not None
        amount_due = None
        if pending and arr is not None and arr.queued_duration_months is not None:
            match = next(
                (p for p in plans if p.duration_months == arr.queued_duration_months), None
            )
            amount_due = match.price if match else None
        views.append(
            SellerPlanServiceView(
                service_id=svc.id,
                service_name=svc.name,
                model=(arr.model.value if arr else FeeModel.Freebie.value),
                status=(arr.status.value if arr else ArrangementStatus.Trial.value),
                valid_until=(arr.valid_until.isoformat() if arr and arr.valid_until else None),
                subscription_enabled=cfg.subscription_enabled,
                subscription_plans=[
                    SubscriptionPlanItem(duration_months=p.duration_months, price=p.price, is_active=p.is_active)
                    for p in plans if p.is_active
                ],
                payment_pending=pending,
                amount_due=amount_due,
                cancel_requested=(arr.cancel_requested if arr else False),
            )
        )
    return SellerPlanView(
        services=views,
        payment_details=SellerPaymentDetails(
            bank_account_name=settings_row.bank_account_name,
            bank_account_number=settings_row.bank_account_number,
            bank_ifsc=settings_row.bank_ifsc,
            upi_id=settings_row.upi_id,
            qr_image_url=settings_row.qr_image_url,
            gstin=settings_row.gstin,
        ),
    )


@seller_router.post("/me/plan/{service_id}/opt-in")
async def opt_in(
    service_id: int,
    body: OptInBody,
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    _profile, store = await _seller_store(session, seller)
    arr = await _arrangement(session, store.id, service_id)
    try:
        payment = await opt_into_subscription(session, arr, body.duration_months)
    except FeeError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    await session.commit()
    await session.refresh(payment)
    return {"payment_id": payment.id, "amount": payment.amount}


@seller_router.post("/me/plan/{service_id}/mark-paid")
async def mark_paid(
    service_id: int,
    body: MarkPaidBody,
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    _profile, store = await _seller_store(session, seller)
    arr = await _arrangement(session, store.id, service_id)
    payment = (
        await session.exec(
            select(FeePayment).where(
                FeePayment.arrangement_id == arr.id,
                FeePayment.status == FeePaymentStatus.Pending,
            )
        )
    ).first()
    if payment is None:
        raise HTTPException(status_code=404, detail={"error": "no_pending_payment"})
    payment.seller_note = body.seller_note
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return {"payment_id": payment.id}


@seller_router.post("/me/plan/{service_id}/cancel")
async def cancel_plan(
    service_id: int,
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    _profile, store = await _seller_store(session, seller)
    arr = await _arrangement(session, store.id, service_id)
    request_cancellation(session, arr)
    await session.commit()
    return {"service_id": service_id, "cancel_requested": True}
