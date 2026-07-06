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
from app.models.admin_audit import AdminActionTargetType
from app.models.base import User
from app.models.catalog import Service, ServiceTranslation
from app.models.notification import NotificationType
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
from app.models.profile import SellerProfile, VerificationStatus
from app.models.store import Store
from app.schemas.platform_fees import (
    ArrangementSummary,
    CompBody,
    ExtendBody,
    MarkPaidBody,
    OptInBody,
    PaymentQueueItem,
    PlatformFeeSettingsPatch,
    PlatformFeeSettingsRead,
    RejectBody,
    SellerPaymentDetails,
    SellerPlanServiceView,
    SellerPlanView,
    ServiceFeeConfigPatch,
    ServiceFeeConfigRead,
    ServiceFeeConfigWithPlans,
    SubscriptionPlanItem,
    SubscriptionPlansPut,
    TerminateBody,
)
from app.services import admin_audit, seller_services
from app.services import platform_fees as fees
from app.services.fee_channels import dispatch_seller_fee_channels
from app.services.fee_lifecycle import (
    FeeError,
    admin_comp_subscription,
    admin_extend,
    admin_terminate,
    confirm_subscription_payment,
    opt_into_subscription,
    reject_payment,
    request_cancellation,
)
from app.services.fee_notifications import notify_seller_fee_event

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


@admin_router.get("/fees/queue", response_model=list[PaymentQueueItem])
async def fee_payment_queue(
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[PaymentQueueItem]:
    rows = (
        await session.exec(
            select(FeePayment, FeeArrangement, Store)
            .join(FeeArrangement, FeeArrangement.id == FeePayment.arrangement_id)
            .join(Store, Store.id == FeeArrangement.store_id)
            .where(FeePayment.status == FeePaymentStatus.Pending)
            .order_by(FeePayment.created_at)  # type: ignore[arg-type]
        )
    ).all()
    # Resolve service names (English) in one batched lookup.
    service_ids = {arr.service_id for _p, arr, _s in rows}
    names: dict[int, str] = {}
    if service_ids:
        for svc_id, name in (
            await session.exec(
                select(ServiceTranslation.service_id, ServiceTranslation.name).where(
                    ServiceTranslation.service_id.in_(service_ids),  # type: ignore[attr-defined]
                    ServiceTranslation.language_code == "en",
                )
            )
        ).all():
            names[svc_id] = name
    return [
        PaymentQueueItem(
            payment_id=p.id,
            arrangement_id=arr.id,
            store_id=store.id,
            store_name=store.name,
            service_id=arr.service_id,
            service_name=names.get(arr.service_id, f"Service {arr.service_id}"),
            kind=p.kind.value,
            amount=p.amount,
            seller_note=p.seller_note,
            pending_since=arr.pending_since.isoformat() if arr.pending_since else None,
            created_at=p.created_at.isoformat(),
        )
        for p, arr, store in rows
    ]


async def _store_seller_id(session: AsyncSession, store_id: int) -> int | None:
    return (
        await session.exec(select(Store.seller_profile_id).where(Store.id == store_id))
    ).first()


async def _pending_payment(session: AsyncSession, payment_id: int) -> FeePayment:
    payment = await session.get(FeePayment, payment_id)
    if payment is None or payment.status != FeePaymentStatus.Pending:
        raise HTTPException(status_code=404, detail={"error": "pending_payment_not_found"})
    return payment


@admin_router.post("/fees/payments/{payment_id}/confirm")
async def confirm_payment(
    payment_id: int,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    payment = await _pending_payment(session, payment_id)
    assert admin.id is not None
    arr = await confirm_subscription_payment(session, payment, admin.id)
    result = {
        "arrangement_id": arr.id,
        "status": arr.status.value,
        "valid_until": arr.valid_until.isoformat() if arr.valid_until else None,
    }
    await notify_seller_fee_event(
        session, store_id=arr.store_id,
        type=NotificationType.FeeActivated, valid_until=arr.valid_until,
    )
    store_id, valid_until = arr.store_id, arr.valid_until
    await session.commit()
    spid = await _store_seller_id(session, store_id)
    if spid is not None:
        dispatch_seller_fee_channels(spid, NotificationType.FeeActivated.value, valid_until)
    return result


@admin_router.post("/fees/payments/{payment_id}/reject")
async def reject_fee_payment(
    payment_id: int,
    body: RejectBody,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    payment = await _pending_payment(session, payment_id)
    assert admin.id is not None
    await reject_payment(session, payment, admin.id, body.reason)
    await session.commit()
    return {"payment_id": payment_id, "status": "rejected"}


async def _arrangement_with_seller(
    session: AsyncSession, arrangement_id: int
) -> tuple[FeeArrangement, SellerProfile]:
    arr = await session.get(FeeArrangement, arrangement_id)
    if arr is None:
        raise HTTPException(status_code=404, detail={"error": "arrangement_not_found"})
    store = await session.get(Store, arr.store_id)
    if store is None:
        raise HTTPException(status_code=404, detail={"error": "store_not_found"})
    profile = await session.get(SellerProfile, store.seller_profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail={"error": "seller_not_found"})
    if profile.verification_status != VerificationStatus.Approved:
        raise HTTPException(status_code=409, detail={"error": "seller_not_active"})
    return arr, profile


def _arr_before(arr: FeeArrangement) -> dict:  # type: ignore[type-arg]
    return {
        "model": arr.model.value,
        "status": arr.status.value,
        "valid_until": arr.valid_until.isoformat() if arr.valid_until else None,
    }


@admin_router.get(
    "/fees/arrangements/{store_id}", response_model=list[ArrangementSummary]
)
async def admin_list_arrangements(
    store_id: int,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[ArrangementSummary]:
    arrs = (
        await session.exec(
            select(FeeArrangement).where(FeeArrangement.store_id == store_id)
        )
    ).all()
    service_ids = {a.service_id for a in arrs}
    names: dict[int, str] = {}
    if service_ids:
        for sid, name in (
            await session.exec(
                select(ServiceTranslation.service_id, ServiceTranslation.name).where(
                    ServiceTranslation.service_id.in_(service_ids),  # type: ignore[attr-defined]
                    ServiceTranslation.language_code == "en",
                )
            )
        ).all():
            names[sid] = name
    return [
        ArrangementSummary(
            id=a.id,
            service_id=a.service_id,
            service_name=names.get(a.service_id, f"Service {a.service_id}"),
            model=a.model.value,
            status=a.status.value,
            valid_until=a.valid_until.isoformat() if a.valid_until else None,
            cancel_requested=a.cancel_requested,
            pending=a.pending_since is not None,
        )
        for a in arrs
    ]


@admin_router.post("/fees/arrangements/{arrangement_id}/extend")
async def admin_extend_arrangement(
    arrangement_id: int,
    body: ExtendBody,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    arr, profile = await _arrangement_with_seller(session, arrangement_id)
    assert admin.id is not None and profile.id is not None
    before = _arr_before(arr)
    admin_extend(session, arr, body.days, admin.id)
    after = _arr_before(arr)
    await admin_audit.log(
        session=session, admin_user_id=admin.id, target_seller_id=profile.id,
        target_type=AdminActionTargetType.SellerProfile, target_id=profile.id,
        action="fee.extend", before_json=before, after_json=after, reason=body.reason,
    )
    await session.commit()
    return {"arrangement_id": arrangement_id, "valid_until": after["valid_until"]}


@admin_router.post("/fees/arrangements/{arrangement_id}/terminate")
async def admin_terminate_arrangement(
    arrangement_id: int,
    body: TerminateBody,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    arr, profile = await _arrangement_with_seller(session, arrangement_id)
    assert admin.id is not None and profile.id is not None
    before = _arr_before(arr)
    admin_terminate(session, arr, body.reason, admin.id)
    await admin_audit.log(
        session=session, admin_user_id=admin.id, target_seller_id=profile.id,
        target_type=AdminActionTargetType.SellerProfile, target_id=profile.id,
        action="fee.terminate", before_json=before, after_json=_arr_before(arr),
        reason=body.reason,
    )
    await notify_seller_fee_event(
        session, store_id=arr.store_id, type=NotificationType.FeeSuspended,
    )
    store_id = arr.store_id
    await session.commit()
    spid = await _store_seller_id(session, store_id)
    if spid is not None:
        dispatch_seller_fee_channels(spid, NotificationType.FeeSuspended.value, None)
    return {"arrangement_id": arrangement_id, "status": "suspended"}


@admin_router.post("/fees/arrangements/{arrangement_id}/comp")
async def admin_comp_arrangement(
    arrangement_id: int,
    body: CompBody,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    arr, profile = await _arrangement_with_seller(session, arrangement_id)
    assert admin.id is not None and profile.id is not None
    before = _arr_before(arr)
    admin_comp_subscription(session, arr, body.duration_months, admin.id)
    after = _arr_before(arr)
    await admin_audit.log(
        session=session, admin_user_id=admin.id, target_seller_id=profile.id,
        target_type=AdminActionTargetType.SellerProfile, target_id=profile.id,
        action="fee.comp", before_json=before, after_json=after, reason=body.reason,
    )
    await notify_seller_fee_event(
        session, store_id=arr.store_id,
        type=NotificationType.FeeActivated, valid_until=arr.valid_until,
    )
    store_id, valid_until = arr.store_id, arr.valid_until
    await session.commit()
    spid = await _store_seller_id(session, store_id)
    if spid is not None:
        dispatch_seller_fee_channels(spid, NotificationType.FeeActivated.value, valid_until)
    return {"arrangement_id": arrangement_id, "status": after["status"], "valid_until": after["valid_until"]}


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
