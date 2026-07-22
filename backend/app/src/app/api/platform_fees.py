# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Admin platform-fee configuration.

`admin_router` mounted at /api/v1/admin. Global settings + per-service fee config
+ subscription-plan pricing."""
from collections.abc import Awaitable, Callable
from datetime import datetime

import anyio
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.security import get_current_admin, get_current_seller
from app.db.session import get_db_session
from app.models.admin_audit import AdminActionTargetType
from app.models.base import User
from app.models.catalog import Service, ServiceTranslation
from app.models.notification import NotificationType
from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeInvoice,
    FeeModel,
    FeePayment,
    FeePaymentKind,
    FeePaymentStatus,
    PlatformFeeSettings,
    ServiceFeeConfig,
    ServiceSubscriptionPlan,
)
from app.models.profile import SellerProfile, VerificationStatus
from app.models.store import Store
from app.schemas.platform_fees import (
    AdminSwitchBody,
    ApplyCreditBody,
    ArrangementSummary,
    CompBody,
    CreditAdjustBody,
    CreditAmountBody,
    ExtendBody,
    ForfeitBody,
    InvoiceView,
    MarkPaidBody,
    OptInBody,
    OrderValueOptInBody,
    PaymentQueueItem,
    PayPerTxnOptInBody,
    PlatformFeeSettingsPatch,
    PlatformFeeSettingsRead,
    RefundDepositBody,
    RejectBody,
    SellerPaymentDetails,
    SellerPlanServiceView,
    SellerPlanView,
    ServiceFeeConfigPatch,
    ServiceFeeConfigRead,
    ServiceFeeConfigWithPlans,
    StoreCreditView,
    SubscriptionPlanItem,
    SubscriptionPlansPut,
    TerminateBody,
    TopUpBody,
)
from app.services import admin_audit, seller_services, store_credit
from app.services import platform_fees as fees
from app.services.fee_channels import dispatch_seller_fee_channels
from app.services.fee_lifecycle import (
    FeeError,
    admin_comp_subscription,
    admin_extend,
    admin_switch_model,
    admin_terminate,
    apply_credit_to_arrangement,
    confirm_pay_per_txn_topup,
    confirm_subscription_payment,
    create_top_up,
    opt_into_pay_per_transaction,
    opt_into_subscription,
    reject_payment,
    request_cancellation,
    seller_switch_from_ppt,
)
from app.services.fee_notifications import notify_seller_fee_event
from app.services.fee_order_value import (
    IST,
    confirm_invoice_payment,
    confirm_order_value_deposit,
    create_invoice_payment,
    forfeit_deposit,
    generate_final_order_value_invoice,
    opt_into_order_value,
    refund_deposit,
)
from app.services.image_processing import ImageValidationError, process_image
from app.services.image_storage import get_image_storage

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


@admin_router.post("/fees/settings/qr", response_model=PlatformFeeSettingsRead)
async def upload_fee_qr(
    file: UploadFile = File(...),
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformFeeSettingsRead:
    """Upload a payment-QR image (validated + WebP-encoded via the shared image
    pipeline), store it, and set it as the global `qr_image_url`."""
    raw = await file.read()
    try:
        data, digest = await anyio.to_thread.run_sync(
            process_image, raw, settings.IMAGE_MAX_DIMENSION_PX
        )
    except ImageValidationError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)}) from exc
    url = await get_image_storage().save(f"fee-qr/{digest}.webp", data, "image/webp")
    row = await fees.get_or_create_settings(session)
    row.qr_image_url = url
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
        order_value_payment_days=c.order_value_payment_days,
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
    notif: NotificationType | None
    if payment.kind == FeePaymentKind.PayPerTxnTopUp:
        # confirm_pay_per_txn_topup records the single correct in-app notification
        # itself (FeeActivated / FeeReactivated / None) — do NOT re-notify here.
        arr, notif = await confirm_pay_per_txn_topup(session, payment, admin.id)
    elif payment.kind == FeePaymentKind.SubscriptionFee:
        arr = await confirm_subscription_payment(session, payment, admin.id)
        notif = NotificationType.FeeActivated
        await notify_seller_fee_event(
            session, store_id=arr.store_id, type=notif, valid_until=arr.valid_until,
        )
    elif payment.kind == FeePaymentKind.SecurityDeposit:
        # confirm_order_value_deposit records the single FeeActivated in-app
        # notification itself — do NOT re-notify here.
        arr, notif = await confirm_order_value_deposit(session, payment, admin.id)
    elif payment.kind == FeePaymentKind.OrderValueInvoice:
        # confirm_invoice_payment records the single FeeReactivated in-app
        # notification itself (only when it reactivates) — do NOT re-notify here.
        arr, notif = await confirm_invoice_payment(session, payment, admin.id)
    else:
        raise HTTPException(
            status_code=400, detail={"error": "unsupported_payment_kind"}
        )
    result = {
        "arrangement_id": arr.id,
        "status": arr.status.value,
        "valid_until": arr.valid_until.isoformat() if arr.valid_until else None,
    }
    store_id, valid_until = arr.store_id, arr.valid_until
    await session.commit()
    if notif is not None:
        spid = await _store_seller_id(session, store_id)
        if spid is not None:
            dispatch_seller_fee_channels(spid, notif.value, valid_until)
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
    # Order Value % exit: bill trailing completed sales as a final partial invoice
    # before suspending (deposit is then settled via the refund-deposit action).
    if arr.model == FeeModel.OrderValuePercent:
        await generate_final_order_value_invoice(session, arr, datetime.now(IST).date())
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


@admin_router.post("/fees/arrangements/{arrangement_id}/forfeit")
async def admin_forfeit_deposit(
    arrangement_id: int,
    body: ForfeitBody,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    arr, profile = await _arrangement_with_seller(session, arrangement_id)
    assert admin.id is not None and profile.id is not None
    if arr.model != FeeModel.OrderValuePercent:
        raise HTTPException(status_code=409, detail={"error": "not_order_value"})
    before = {
        "security_deposit_amount": arr.security_deposit_amount,
        "balance": arr.balance,
    }
    try:
        _arr, notif = await forfeit_deposit(
            session, arr, body.amount, admin.id,
            invoice_id=body.invoice_id, reason=body.reason,
        )
    except FeeError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    after = {
        "security_deposit_amount": arr.security_deposit_amount,
        "balance": arr.balance,
    }
    await admin_audit.log(
        session=session, admin_user_id=admin.id, target_seller_id=profile.id,
        target_type=AdminActionTargetType.SellerProfile, target_id=profile.id,
        action="fee.order_value.forfeit", before_json=before, after_json=after,
        reason=body.reason,
    )
    store_id = arr.store_id
    status_value = arr.status.value
    await session.commit()
    if notif is not None:  # forfeit cleared the last unpaid invoice → reactivated
        spid = await _store_seller_id(session, store_id)
        if spid is not None:
            dispatch_seller_fee_channels(spid, notif.value, None)
    return {
        "arrangement_id": arrangement_id,
        "status": status_value,
        "security_deposit_amount": after["security_deposit_amount"],
        "balance": after["balance"],
    }


@admin_router.post("/fees/arrangements/{arrangement_id}/refund-deposit")
async def admin_refund_deposit(
    arrangement_id: int,
    body: RefundDepositBody,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    arr, profile = await _arrangement_with_seller(session, arrangement_id)
    assert admin.id is not None and profile.id is not None
    if arr.model != FeeModel.OrderValuePercent:
        raise HTTPException(status_code=409, detail={"error": "not_order_value"})
    before = {"security_deposit_amount": arr.security_deposit_amount, "balance": arr.balance}
    try:
        refunded = await refund_deposit(session, arr, body.mode, admin.id, note=body.note)
    except (FeeError, store_credit.StoreCreditError) as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    await admin_audit.log(
        session=session, admin_user_id=admin.id, target_seller_id=profile.id,
        target_type=AdminActionTargetType.SellerProfile, target_id=profile.id,
        action="fee.order_value.refund_deposit", before_json=before,
        after_json={"security_deposit_amount": arr.security_deposit_amount, "balance": arr.balance},
        reason=body.note or f"deposit refund ({body.mode})",
    )
    await session.commit()
    return {"arrangement_id": arrangement_id, "refunded": refunded, "mode": body.mode}


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


@admin_router.post("/fees/arrangements/{arrangement_id}/switch")
async def admin_switch_arrangement(
    arrangement_id: int,
    body: AdminSwitchBody,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    """Admin force-switches an arrangement to another model at ANY balance
    (disposition picks how leftover PPT balance is settled). Bypasses seller
    guards + gating."""
    arr, profile = await _arrangement_with_seller(session, arrangement_id)
    assert admin.id is not None and profile.id is not None
    try:
        target = FeeModel(body.target_model)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": "bad_target_model"}) from exc
    before = _arr_before(arr)
    try:
        await admin_switch_model(
            session, arr, target_model=target,
            target_duration_months=body.duration_months,
            disposition=body.disposition, admin_user_id=admin.id,
        )
    except (FeeError, store_credit.StoreCreditError) as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    after = _arr_before(arr)
    await admin_audit.log(
        session=session, admin_user_id=admin.id, target_seller_id=profile.id,
        target_type=AdminActionTargetType.SellerProfile, target_id=profile.id,
        action="fee.switch", before_json=before, after_json=after,
        reason=body.reason.strip(),
    )
    # Notify the seller of the model change (only when it lands them on a live
    # paid plan; a switch to Freebie-trial needs no "active" notice).
    notif = (
        NotificationType.FeeActivated
        if arr.status == ArrangementStatus.Active
        else None
    )
    if notif is not None:
        await notify_seller_fee_event(
            session, store_id=arr.store_id, type=notif, valid_until=arr.valid_until,
        )
    # Capture before commit — the request session expires attributes on commit.
    store_id, valid_until = arr.store_id, arr.valid_until
    await session.commit()
    if notif is not None:
        spid = await _store_seller_id(session, store_id)
        if spid is not None:
            dispatch_seller_fee_channels(spid, notif.value, valid_until)
    return {"arrangement_id": arrangement_id, "status": after["status"], "model": after["model"]}


async def _admin_store(
    session: AsyncSession, store_id: int
) -> tuple[Store, SellerProfile]:
    store = await session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail={"error": "store_not_found"})
    profile = await session.get(SellerProfile, store.seller_profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail={"error": "seller_not_found"})
    return store, profile


async def _credit_action(
    session: AsyncSession, store_id: int, admin: User, reason: str, action: str,
    mutate: Callable[[Store], Awaitable[None]],
) -> dict[str, object]:
    """Run a wallet-credit mutation on a store with audit + commit. `mutate` is
    an async callable taking the loaded Store."""
    store, profile = await _admin_store(session, store_id)
    assert admin.id is not None and profile.id is not None
    before = {"fee_credit_balance": store.fee_credit_balance}
    try:
        await mutate(store)
    except store_credit.StoreCreditError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    await admin_audit.log(
        session=session, admin_user_id=admin.id, target_seller_id=profile.id,
        target_type=AdminActionTargetType.SellerProfile, target_id=profile.id,
        action=action, before_json=before,
        after_json={"fee_credit_balance": store.fee_credit_balance},
        reason=reason.strip(),
    )
    await session.commit()
    await session.refresh(store)
    return {"store_id": store_id, "fee_credit_balance": store.fee_credit_balance}


@admin_router.post("/fees/stores/{store_id}/credit/grant")
async def admin_credit_grant(
    store_id: int, body: CreditAmountBody,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    async def _m(store: Store) -> None:
        await store_credit.grant(
            session, store, body.amount, actor=f"admin:{admin.id}", note=body.reason
        )
    return await _credit_action(session, store_id, admin, body.reason, "fee.credit_grant", _m)


@admin_router.post("/fees/stores/{store_id}/credit/adjust")
async def admin_credit_adjust(
    store_id: int, body: CreditAdjustBody,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    if body.amount == 0:
        raise HTTPException(status_code=422, detail={"error": "zero_amount"})

    async def _m(store: Store) -> None:
        await store_credit.grant(
            session, store, body.amount, actor=f"admin:{admin.id}", note=body.reason
        )
    return await _credit_action(session, store_id, admin, body.reason, "fee.credit_adjust", _m)


@admin_router.post("/fees/stores/{store_id}/credit/cash-out")
async def admin_credit_cash_out(
    store_id: int, body: CreditAmountBody,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    async def _m(store: Store) -> None:
        await store_credit.cash_out(
            session, store, body.amount, actor=f"admin:{admin.id}", note=body.reason
        )
    return await _credit_action(session, store_id, admin, body.reason, "fee.credit_cash_out", _m)


@admin_router.post("/fees/arrangements/{arrangement_id}/apply-credit")
async def admin_apply_credit(
    arrangement_id: int, body: CreditAmountBody,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    """Admin applies the store's wallet credit to a PPT arrangement's balance on
    the seller's behalf (same effect as the seller's apply-credit)."""
    arr, profile = await _arrangement_with_seller(session, arrangement_id)
    assert admin.id is not None and profile.id is not None
    before = {"balance": arr.balance, "status": arr.status.value}
    try:
        applied = await apply_credit_to_arrangement(session, arr, body.amount)
    except FeeError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    after = {"balance": arr.balance, "status": arr.status.value}
    await admin_audit.log(
        session=session, admin_user_id=admin.id, target_seller_id=profile.id,
        target_type=AdminActionTargetType.SellerProfile, target_id=profile.id,
        action="fee.credit_apply", before_json=before, after_json=after,
        reason=body.reason.strip(),
    )
    await session.commit()
    return {"arrangement_id": arrangement_id, "applied": applied, **after}


@admin_router.get("/fees/stores/credit", response_model=list[StoreCreditView])
async def admin_list_credit(
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[StoreCreditView]:
    rows = (
        await session.exec(select(Store).where(Store.fee_credit_balance != 0.0))
    ).all()
    return [
        StoreCreditView(
            store_id=s.id, store_name=s.name, fee_credit_balance=s.fee_credit_balance
        )
        for s in rows
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
        is_ppt = arr is not None and arr.model == FeeModel.PayPerTransaction
        ppt_balance = arr.balance if (arr is not None and is_ppt) else None
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
                pay_per_txn_enabled=cfg.pay_per_txn_enabled,
                pay_per_txn_fee=cfg.pay_per_txn_fee,
                pay_per_txn_min_deposit=cfg.pay_per_txn_min_deposit,
                balance=ppt_balance,
                low_balance_threshold=(
                    cfg.pay_per_txn_low_balance_threshold if is_ppt else None
                ),
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
        fee_credit_balance=store.fee_credit_balance,
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


@seller_router.post("/me/plan/{service_id}/pay-per-transaction/opt-in")
async def opt_in_ppt(
    service_id: int,
    body: PayPerTxnOptInBody,
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    _profile, store = await _seller_store(session, seller)
    arr = await _arrangement(session, store.id, service_id)
    try:
        payment = await opt_into_pay_per_transaction(
            session, arr, body.deposit_amount, use_credit=body.use_credit
        )
    except FeeError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    await session.commit()
    if payment is None:
        return {"payment_id": None, "status": "active"}
    await session.refresh(payment)
    return {"payment_id": payment.id, "amount": payment.amount}


@seller_router.post("/me/plan/{service_id}/order-value/opt-in")
async def opt_in_order_value(
    service_id: int,
    body: OrderValueOptInBody,
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    _profile, store = await _seller_store(session, seller)
    arr = await _arrangement(session, store.id, service_id)
    try:
        payment = await opt_into_order_value(session, arr, body.deposit_amount)
    except FeeError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    await session.commit()
    await session.refresh(payment)
    return {"payment_id": payment.id, "amount": payment.amount}


def _invoice_view(inv: FeeInvoice) -> InvoiceView:
    return InvoiceView(
        id=inv.id,  # type: ignore[arg-type]
        arrangement_id=inv.arrangement_id,
        service_id=inv.service_id,
        period_start=inv.period_start.isoformat(),
        period_end=inv.period_end.isoformat(),
        sales_total=inv.sales_total,
        fee_percent_snapshot=inv.fee_percent_snapshot,
        amount_due=inv.amount_due,
        status=inv.status.value,
        issued_on=inv.issued_on.isoformat(),
        due_date=inv.due_date.isoformat(),
        suspend_after=inv.suspend_after.isoformat(),
        paid_at=inv.paid_at.isoformat() if inv.paid_at else None,
    )


@seller_router.get(
    "/me/plan/{service_id}/invoices", response_model=list[InvoiceView]
)
async def list_my_invoices(
    service_id: int,
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> list[InvoiceView]:
    _profile, store = await _seller_store(session, seller)
    arr = await _arrangement(session, store.id, service_id)
    invoices = (
        await session.exec(
            select(FeeInvoice)
            .where(FeeInvoice.arrangement_id == arr.id)
            .order_by(FeeInvoice.period_start.desc())  # type: ignore[attr-defined]
        )
    ).all()
    return [_invoice_view(inv) for inv in invoices]


@seller_router.post("/me/plan/{service_id}/invoices/{invoice_id}/mark-paid")
async def mark_invoice_paid(
    service_id: int,
    invoice_id: int,
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    _profile, store = await _seller_store(session, seller)
    arr = await _arrangement(session, store.id, service_id)
    try:
        payment = await create_invoice_payment(session, arr, invoice_id)
    except FeeError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    await session.commit()
    await session.refresh(payment)
    return {"payment_id": payment.id, "amount": payment.amount}


@admin_router.get(
    "/fees/arrangements/{arrangement_id}/invoices", response_model=list[InvoiceView]
)
async def admin_list_arrangement_invoices(
    arrangement_id: int,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[InvoiceView]:
    arr = await session.get(FeeArrangement, arrangement_id)
    if arr is None:
        raise HTTPException(status_code=404, detail={"error": "arrangement_not_found"})
    invoices = (
        await session.exec(
            select(FeeInvoice)
            .where(FeeInvoice.arrangement_id == arrangement_id)
            .order_by(FeeInvoice.period_start.desc())  # type: ignore[attr-defined]
        )
    ).all()
    return [_invoice_view(inv) for inv in invoices]


@seller_router.post("/me/plan/{service_id}/top-up")
async def top_up(
    service_id: int,
    body: TopUpBody,
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    _profile, store = await _seller_store(session, seller)
    arr = await _arrangement(session, store.id, service_id)
    try:
        payment = await create_top_up(session, arr, body.amount)
    except FeeError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    await session.commit()
    await session.refresh(payment)
    return {"payment_id": payment.id, "amount": payment.amount}


@seller_router.post("/me/plan/{service_id}/apply-credit")
async def apply_credit(
    service_id: int,
    body: ApplyCreditBody,
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    _profile, store = await _seller_store(session, seller)
    arr = await _arrangement(session, store.id, service_id)
    try:
        applied = await apply_credit_to_arrangement(session, arr, body.amount)
    except FeeError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    await session.commit()
    await session.refresh(arr)
    return {"applied": applied, "balance": arr.balance, "status": arr.status.value}


@seller_router.post("/me/plan/{service_id}/switch")
async def switch_model(
    service_id: int,
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    """Seller leaves Pay-Per-Transaction (positive balance → wallet credit).
    Blocked with 400 balance_negative when balance < 0 (settle first)."""
    _profile, store = await _seller_store(session, seller)
    arr = await _arrangement(session, store.id, service_id)
    try:
        await seller_switch_from_ppt(session, arr)
    except (FeeError, store_credit.StoreCreditError) as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    await session.commit()
    return {"service_id": service_id, "status": "switched"}
