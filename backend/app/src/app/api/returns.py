# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Return-order endpoints for customers, sellers, and admins.

Four routers, mounted at four prefixes (mirrors `platform_fees.py`):
  * ``router``              → /returns        (customer)
  * ``store_credit_router`` → /store-credit   (customer; a balance outlives the
                                               return that created it)
  * ``seller_router``       → /sellers
  * ``admin_router``        → /admin
"""
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.otp import (
    CodeExpired,
    InvalidCode,
    RateLimited,
    TooManyAttempts,
    consume_otp_key,
    request_otp,
    verify_otp,
)
from app.core.redis import get_redis
from app.core.security import (
    get_current_admin,
    get_current_customer,
    get_current_seller,
)
from app.db.session import get_db_session
from app.models.admin_audit import AdminActionTargetType
from app.models.base import AccountStatus, User
from app.models.commerce import Order
from app.models.consent import PolicyKind
from app.models.notification import NotificationType
from app.models.profile import CustomerProfile, SellerProfile
from app.models.returns import (
    CustomerStoreCredit,
    ReturnInitiator,
    ReturnRequest,
    ReturnRequestItem,
    ReturnStatus,
)
from app.models.store import Store
from app.schemas.returns import (
    AdminReturnAcceptBody,
    AdminReturnReasonBody,
    ReturnAcceptBody,
    ReturnConfirmBody,
    ReturnCreateBody,
    ReturnCreateOnBehalfBody,
    ReturnEligibilityLine,
    ReturnEligibilityRead,
    ReturnItemRead,
    ReturnPaymentConfirmBody,
    ReturnRead,
    ReturnRejectBody,
    StoreCreditBalanceRead,
    StoreCreditEntryRead,
)
from app.services import customer_store_credit as store_credit_svc
from app.services import returns as returns_svc
from app.services.admin_audit import log as audit_log
from app.services.consent import get_current_version
from app.services.notifications import record_return_notification
from app.services.return_comms import dispatch_return_otp, dispatch_return_status

router = APIRouter()
store_credit_router = APIRouter()
seller_router = APIRouter()
admin_router = APIRouter()

logger = logging.getLogger(__name__)


async def _customer_profile_id(session: AsyncSession, user: User) -> int:
    profile_id = (
        await session.exec(
            select(CustomerProfile.id).where(CustomerProfile.user_id == user.id)
        )
    ).first()
    if profile_id is None:
        raise returns_svc.ReturnError(404, "customer_profile_not_found")
    return int(profile_id)


async def _owned_order(session: AsyncSession, order_id: int, profile_id: int) -> Order:
    order = await session.get(Order, order_id)
    if order is None:
        raise returns_svc.ReturnError(404, "order_not_found")
    if order.customer_profile_id != profile_id:
        raise returns_svc.ReturnError(403, "forbidden")
    return order


@router.get("/eligibility/{order_id}", response_model=ReturnEligibilityRead)
async def return_eligibility(
    order_id: int,
    user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnEligibilityRead:
    profile_id = await _customer_profile_id(session, user)
    order = await _owned_order(session, order_id, profile_id)
    result = await returns_svc.compute_eligibility(
        session, order=order, customer_profile_id=profile_id
    )
    agreement_version = await get_current_version(session, PolicyKind.return_agreement)
    return ReturnEligibilityRead(
        order_id=order_id,
        eligible=result.eligible,
        reason_code=result.reason_code,
        window_expires_at=result.window_expires_at,
        delivery_fee=result.delivery_fee,
        full_order_available=result.full_order_available,
        agreement_version=agreement_version or None,
        lines=[
            ReturnEligibilityLine(
                order_item_id=line.order_item_id, product_name=line.product_name,
                unit_price=line.unit_price, quantity=line.quantity,
                line_total=line.line_total, returnable=line.returnable,
                lock_reason=line.lock_reason,
            )
            for line in result.lines
        ],
    )


def _pk(value: int | None) -> int:
    """Narrow a persisted row's primary key (see services/returns._pk)."""
    assert value is not None
    return value


def _serialize(
    request: ReturnRequest,
    items: list[ReturnRequestItem],
    *,
    include_receipt_otp: bool = False,
) -> ReturnRead:
    return ReturnRead(
        id=_pk(request.id), order_id=request.order_id, store_id=request.store_id,
        seller_profile_id=request.seller_profile_id, status=request.status,
        initiated_by=request.initiated_by, is_full_order=request.is_full_order,
        reason_code=request.reason_code, reason_note=request.reason_note,
        items_amount=request.items_amount,
        delivery_fee_amount=request.delivery_fee_amount,
        total_amount=request.total_amount,
        settlement_choice=request.settlement_choice,
        credit_reversal_amount=request.credit_reversal_amount,
        store_credit_amount=request.store_credit_amount,
        payment_amount=request.payment_amount,
        rejection_reason=request.rejection_reason,
        agreement_policy_version=request.agreement_policy_version,
        window_expires_at=request.window_expires_at,
        confirm_expires_at=request.confirm_expires_at,
        handover_expires_at=request.handover_expires_at,
        created_at=request.created_at,
        items=[
            ReturnItemRead(
                order_item_id=i.order_item_id, product_name=i.product_name_snapshot,
                unit_price=i.unit_price_snapshot, quantity=i.quantity,
                line_total=i.line_total,
            )
            for i in items
        ],
        receipt_otp=request.receipt_otp if include_receipt_otp else None,
    )


async def _load_items(
    session: AsyncSession, return_id: int
) -> list[ReturnRequestItem]:
    return list(
        (
            await session.exec(
                select(ReturnRequestItem)
                .where(ReturnRequestItem.return_request_id == return_id)
                .order_by(col(ReturnRequestItem.id))
            )
        ).all()
    )


async def _require_agreement_version(session: AsyncSession) -> int:
    """The platform must not invent legal terms — refuse until one is published."""
    version = await get_current_version(session, PolicyKind.return_agreement)
    if not version:
        raise returns_svc.ReturnError(409, "agreement_unavailable")
    return version


async def _send_initiation_otp(
    user_id: int, return_id: int, *, best_effort: bool = False
) -> None:
    """Issue and dispatch the initiation code.

    `best_effort=True` at creation: the return row is already committed and
    holding item locks, so a Redis hiccup must not 500 the caller — they have
    the return id and can retry through /otp/resend.
    """
    redis = await get_redis()
    identifier = f"{user_id}:{return_id}"
    try:
        code = await request_otp(identifier, redis, namespace="return_initiate")
    except RateLimited as exc:
        if best_effort:
            logger.warning("return otp rate-limited return_id=%s", return_id)
            return
        raise returns_svc.ReturnError(
            429, "resend_cooldown", retry_after=exc.retry_after
        ) from exc
    except Exception:
        if not best_effort:
            raise
        logger.exception("return otp dispatch failed return_id=%s", return_id)
        return
    dispatch_return_otp(user_id, return_id, code, "initiate")


# ─── Notifications ───────────────────────────────────────────────────────

# One place for the six English strings, mirroring _STATUS_COPY in api/orders.py.
def _return_copy(
    request: ReturnRequest, event_key: str
) -> tuple[str, str, str, NotificationType]:
    rid = request.id
    if event_key == "return_initiated":
        return (
            f"Confirm return #{rid}",
            "A return was started for your order. Review the agreement and "
            "confirm it with the code we sent you.",
            "awaiting_customer_confirmation",
            NotificationType.ReturnStatusUpdate,
        )
    if event_key == "return_confirmed":
        return (
            f"Handover code for return #{rid}",
            f"Show code {request.receipt_otp} to the store when you hand the "
            "items over.",
            "active",
            NotificationType.ReturnReceiptOtp,
        )
    if event_key == "return_accepted":
        return (
            f"Return #{rid} accepted",
            "The store received your items. Check the app for how the amount "
            "is being settled.",
            request.status.value,
            NotificationType.ReturnStatusUpdate,
        )
    if event_key == "return_rejected":
        return (
            f"Return #{rid} was not accepted",
            f"Reason: {request.rejection_reason or 'not given'}. Settle this "
            "directly with the store, per the return agreement.",
            "rejected",
            NotificationType.ReturnStatusUpdate,
        )
    if event_key == "return_withdrawn":
        return (
            f"Return #{rid} withdrawn",
            "This return was withdrawn. The items are free to return again if "
            "the order's return window is still open.",
            "withdrawn",
            NotificationType.ReturnStatusUpdate,
        )
    if event_key == "return_expired":
        return (
            f"Return #{rid} expired",
            "It was not completed in time. The items are free to return again "
            "if the order's return window is still open.",
            "expired",
            NotificationType.ReturnStatusUpdate,
        )
    return (
        f"Return #{rid} closed",
        "Your return is complete.",
        "closed",
        NotificationType.ReturnStatusUpdate,
    )


async def _notify_return(
    session: AsyncSession, request: ReturnRequest, event_key: str
) -> None:
    """Best-effort in-app + email + WhatsApp. Never raises into the request
    path — a notification outage must not fail a return that already committed.
    """
    # Capture before any commit: commit expires ORM attributes, and reading
    # request.id afterwards triggers a sync lazy load -> MissingGreenlet.
    return_id = _pk(request.id)
    try:
        owner = (
            await session.exec(
                select(User)
                .join(CustomerProfile, col(CustomerProfile.user_id) == User.id)
                .where(CustomerProfile.id == request.customer_profile_id)
            )
        ).first()
        # Skip all comms for a non-active account, matching
        # record_and_dispatch_notification in api/orders.py.
        if owner is not None and owner.account_status == AccountStatus.active:
            title, body, status_value, notif_type = _return_copy(request, event_key)
            await record_return_notification(
                session, return_request_id=return_id, type=notif_type,
                title=title, body=body, status_value=status_value,
                customer_profile_id=request.customer_profile_id,
            )
            if event_key == "return_confirmed":
                await record_return_notification(
                    session, return_request_id=return_id,
                    type=NotificationType.SellerReturnRequest,
                    title=f"Return #{request.id} confirmed",
                    body=(
                        "A customer confirmed a return. Collect the items and "
                        "enter their handover code to accept it."
                    ),
                    status_value="active",
                    seller_profile_id=request.seller_profile_id,
                )
            await session.commit()
    except Exception:  # noqa: BLE001 - notifications are never load-bearing
        logger.exception("return notification failed return_id=%s", return_id)
        await session.rollback()
    # Commit (or rollback) expires the caller's instance; refresh so the
    # handler can still serialize the return it just mutated.
    try:
        await session.refresh(request)
    except Exception:  # noqa: BLE001 - best effort, same as above
        logger.exception("could not refresh return after notify id=%s", return_id)
    dispatch_return_status(return_id, event_key)


@router.post("", response_model=ReturnRead, status_code=201)
async def create_return_request(
    body: ReturnCreateBody,
    user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnRead:
    profile_id = await _customer_profile_id(session, user)
    order = await _owned_order(session, body.order_id, profile_id)
    version = await _require_agreement_version(session)
    request = await returns_svc.create_return(
        session, order=order, customer_profile_id=profile_id,
        order_item_ids=body.order_item_ids, reason_code=body.reason_code,
        reason_note=body.reason_note, settlement_choice=body.settlement_choice,
        initiated_by=ReturnInitiator.customer, initiated_by_user_id=_pk(user.id),
        agreement_version=version,
    )
    await session.commit()
    await session.refresh(request)
    await _send_initiation_otp(_pk(user.id), _pk(request.id), best_effort=True)
    await _notify_return(session, request, "return_initiated")
    return _serialize(request, await _load_items(session, _pk(request.id)))


@router.post("/{return_id}/otp/resend", status_code=200)
async def resend_initiation_otp(
    return_id: int,
    user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, bool]:
    profile_id = await _customer_profile_id(session, user)
    request = await session.get(ReturnRequest, return_id)
    if request is None or request.customer_profile_id != profile_id:
        raise returns_svc.ReturnError(404, "return_not_found")
    if request.status != ReturnStatus.awaiting_customer_confirmation:
        raise returns_svc.ReturnError(409, "return_not_awaiting_confirmation")
    await _send_initiation_otp(_pk(user.id), return_id)
    return {"sent": True}


async def _owned_return(
    session: AsyncSession, return_id: int, profile_id: int, *, lock: bool = False
) -> ReturnRequest:
    """`lock=True` on every path that mutates the return — see
    `returns_svc.lock_return` for why an unlocked read-then-write is unsafe."""
    request = (
        await returns_svc.lock_return(session, return_id)
        if lock
        else await session.get(ReturnRequest, return_id)
    )
    if request is None or request.customer_profile_id != profile_id:
        raise returns_svc.ReturnError(404, "return_not_found")
    return request


@router.post("/{return_id}/confirm", response_model=ReturnRead)
async def confirm_return_request(
    return_id: int,
    body: ReturnConfirmBody,
    user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnRead:
    profile_id = await _customer_profile_id(session, user)
    request = await _owned_return(session, return_id, profile_id, lock=True)
    if not body.agreement_accepted:
        raise returns_svc.ReturnError(422, "agreement_not_accepted")
    # Status first, so a stale request fails before we burn an OTP attempt.
    if request.status != ReturnStatus.awaiting_customer_confirmation:
        raise returns_svc.ReturnError(
            409, "illegal_return_transition",
            **{"from": request.status.value, "to": "active"},
        )

    redis = await get_redis()
    identifier = f"{user.id}:{return_id}"
    try:
        await verify_otp(identifier, body.otp, redis, namespace="return_initiate")
    except (CodeExpired, InvalidCode, TooManyAttempts) as exc:
        raise returns_svc.ReturnError(422, "return_otp_invalid") from exc

    await returns_svc.confirm_return(session, request, actor_user_id=_pk(user.id))
    await session.commit()
    await session.refresh(request)
    await consume_otp_key(identifier, redis, namespace="return_initiate")
    # Fires before the code is hidden from later payloads — the notification and
    # the WhatsApp message both carry it.
    await _notify_return(session, request, "return_confirmed")
    return _serialize(
        request, await _load_items(session, return_id), include_receipt_otp=True
    )


@router.post("/{return_id}/withdraw", response_model=ReturnRead)
async def withdraw_return_request(
    return_id: int,
    user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnRead:
    profile_id = await _customer_profile_id(session, user)
    request = await _owned_return(session, return_id, profile_id, lock=True)
    await returns_svc.withdraw_return(session, request, actor_user_id=_pk(user.id))
    await session.commit()
    await session.refresh(request)
    await _notify_return(session, request, "return_withdrawn")
    return _serialize(request, await _load_items(session, return_id))


@router.post("/{return_id}/receipt-otp/resend", response_model=ReturnRead)
async def resend_receipt_otp(
    return_id: int,
    user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnRead:
    """Reissue the handover code the seller types. Customer-only: they hold it."""
    profile_id = await _customer_profile_id(session, user)
    request = await _owned_return(session, return_id, profile_id, lock=True)
    await returns_svc.reissue_receipt_otp(session, request)
    await session.commit()
    await session.refresh(request)
    await _notify_return(session, request, "return_confirmed")
    return _serialize(
        request, await _load_items(session, return_id), include_receipt_otp=True
    )


@router.post("/{return_id}/payment/otp/request", status_code=200)
async def request_payment_otp(
    return_id: int,
    user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, bool]:
    profile_id = await _customer_profile_id(session, user)
    request = await _owned_return(session, return_id, profile_id)
    if request.status != ReturnStatus.awaiting_payment_confirmation:
        raise returns_svc.ReturnError(409, "return_not_awaiting_payment")

    redis = await get_redis()
    identifier = f"{user.id}:{return_id}"
    try:
        code = await request_otp(identifier, redis, namespace="return_payment")
    except RateLimited as exc:
        raise returns_svc.ReturnError(
            429, "resend_cooldown", retry_after=exc.retry_after
        ) from exc
    dispatch_return_otp(_pk(user.id), return_id, code, "payment")
    return {"sent": True}


@router.post("/{return_id}/payment/confirm", response_model=ReturnRead)
async def confirm_payment_received(
    return_id: int,
    body: ReturnPaymentConfirmBody,
    user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnRead:
    profile_id = await _customer_profile_id(session, user)
    request = await _owned_return(session, return_id, profile_id, lock=True)
    # Status first, so a stale request fails before we burn an OTP attempt.
    if request.status != ReturnStatus.awaiting_payment_confirmation:
        raise returns_svc.ReturnError(
            409, "illegal_return_transition",
            **{"from": request.status.value, "to": "closed"},
        )

    redis = await get_redis()
    identifier = f"{user.id}:{return_id}"
    try:
        await verify_otp(identifier, body.otp, redis, namespace="return_payment")
    except (CodeExpired, InvalidCode, TooManyAttempts) as exc:
        raise returns_svc.ReturnError(422, "return_otp_invalid") from exc

    await returns_svc.close_after_payment(session, request, actor_user_id=_pk(user.id))
    await session.commit()
    await session.refresh(request)
    await consume_otp_key(identifier, redis, namespace="return_payment")
    await _notify_return(session, request, "return_closed")
    return _serialize(request, await _load_items(session, return_id))



# ─── Seller ──────────────────────────────────────────────────────────────


async def _seller_profile_id(session: AsyncSession, user: User) -> int:
    profile_id = (
        await session.exec(
            select(SellerProfile.id).where(SellerProfile.user_id == user.id)
        )
    ).first()
    if profile_id is None:
        raise returns_svc.ReturnError(404, "seller_profile_not_found")
    return int(profile_id)


async def _seller_return(
    session: AsyncSession, return_id: int, user: User, *, lock: bool = False
) -> ReturnRequest:
    request = (
        await returns_svc.lock_return(session, return_id)
        if lock
        else await session.get(ReturnRequest, return_id)
    )
    if request is None or not await returns_svc.seller_owns_return(
        session, user, request
    ):
        raise returns_svc.ReturnError(404, "return_not_found")
    return request


@seller_router.post("/me/returns", response_model=ReturnRead, status_code=201)
async def seller_create_return(
    body: ReturnCreateOnBehalfBody,
    user: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnRead:
    """Seller starts a return for a customer. No seller OTP — the return is
    inert until the customer accepts the agreement and confirms by OTP, which
    is the consent the BRD requires."""
    seller_profile_id = await _seller_profile_id(session, user)
    order = await session.get(Order, body.order_id)
    if order is None or order.customer_profile_id != body.customer_profile_id:
        raise returns_svc.ReturnError(404, "order_not_found")
    # The order must belong to THIS seller's store.
    if await returns_svc.resolve_seller_profile_id(
        session, order.store_id
    ) != seller_profile_id:
        raise returns_svc.ReturnError(404, "order_not_found")

    version = await _require_agreement_version(session)
    request = await returns_svc.create_return(
        session, order=order, customer_profile_id=body.customer_profile_id,
        order_item_ids=body.order_item_ids, reason_code=body.reason_code,
        reason_note=body.reason_note, settlement_choice=body.settlement_choice,
        initiated_by=ReturnInitiator.seller, initiated_by_user_id=_pk(user.id),
        agreement_version=version,
    )
    await session.commit()
    await session.refresh(request)
    owner_user_id = (
        await session.exec(
            select(CustomerProfile.user_id).where(
                CustomerProfile.id == body.customer_profile_id
            )
        )
    ).first()
    if owner_user_id is not None:
        await _send_initiation_otp(
            int(owner_user_id), _pk(request.id), best_effort=True
        )
    await _notify_return(session, request, "return_initiated")
    return _serialize(request, await _load_items(session, _pk(request.id)))


@seller_router.post("/me/returns/{return_id}/accept", response_model=ReturnRead)
async def seller_accept_return(
    return_id: int,
    body: ReturnAcceptBody,
    user: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnRead:
    request = await _seller_return(session, return_id, user, lock=True)
    await returns_svc.accept_return(
        session, request, actor_role="seller", actor_user_id=_pk(user.id),
        otp=body.otp, restock=body.restock,
    )
    await session.commit()
    await session.refresh(request)
    await _notify_return(session, request, "return_accepted")
    return _serialize(request, await _load_items(session, return_id))


@seller_router.post("/me/returns/{return_id}/reject", response_model=ReturnRead)
async def seller_reject_return(
    return_id: int,
    body: ReturnRejectBody,
    user: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnRead:
    request = await _seller_return(session, return_id, user, lock=True)
    await returns_svc.reject_return(
        session, request, actor_role="seller", actor_user_id=_pk(user.id),
        reason=body.reason,
    )
    await session.commit()
    await session.refresh(request)
    await _notify_return(session, request, "return_rejected")
    return _serialize(request, await _load_items(session, return_id))


# ─── Customer + seller listings ──────────────────────────────────────────


@router.get("", response_model=list[ReturnRead])
async def list_my_returns(
    status_filter: Optional[ReturnStatus] = Query(default=None, alias="status"),
    user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> list[ReturnRead]:
    profile_id = await _customer_profile_id(session, user)
    query = select(ReturnRequest).where(
        ReturnRequest.customer_profile_id == profile_id
    )
    if status_filter is not None:
        query = query.where(ReturnRequest.status == status_filter)
    rows = list(
        (
            await session.exec(
                query.order_by(col(ReturnRequest.created_at).desc()).limit(100)
            )
        ).all()
    )
    return [
        _serialize(
            row, await _load_items(session, _pk(row.id)),
            include_receipt_otp=row.status == ReturnStatus.active,
        )
        for row in rows
    ]


@router.get("/{return_id}", response_model=ReturnRead)
async def get_my_return(
    return_id: int,
    user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnRead:
    profile_id = await _customer_profile_id(session, user)
    request = await _owned_return(session, return_id, profile_id)
    return _serialize(
        request, await _load_items(session, return_id),
        include_receipt_otp=request.status == ReturnStatus.active,
    )


@seller_router.get("/me/returns", response_model=list[ReturnRead])
async def list_seller_returns(
    status_filter: Optional[ReturnStatus] = Query(default=None, alias="status"),
    user: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> list[ReturnRead]:
    profile_id = await _seller_profile_id(session, user)
    query = select(ReturnRequest).where(
        ReturnRequest.seller_profile_id == profile_id
    )
    if status_filter is not None:
        query = query.where(ReturnRequest.status == status_filter)
    rows = list(
        (
            await session.exec(
                query.order_by(col(ReturnRequest.created_at).desc()).limit(100)
            )
        ).all()
    )
    # Sellers never see the handover code — they type what the customer shows.
    return [_serialize(row, await _load_items(session, _pk(row.id))) for row in rows]


@seller_router.get("/me/returns/{return_id}", response_model=ReturnRead)
async def get_seller_return(
    return_id: int,
    user: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnRead:
    request = await _seller_return(session, return_id, user)
    return _serialize(request, await _load_items(session, return_id))


# ─── Store credit ────────────────────────────────────────────────────────


@store_credit_router.get("", response_model=list[StoreCreditBalanceRead])
async def list_store_credit(
    user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> list[StoreCreditBalanceRead]:
    profile_id = await _customer_profile_id(session, user)
    accounts = await store_credit_svc.list_balances(session, profile_id)
    out: list[StoreCreditBalanceRead] = []
    for account in accounts:
        store = (
            await session.exec(
                select(Store).where(
                    Store.seller_profile_id == account.seller_profile_id
                )
            )
        ).first()
        out.append(
            StoreCreditBalanceRead(
                seller_profile_id=account.seller_profile_id,
                store_id=store.id if store else None,
                store_name=store.name if store else "Store",
                balance=account.balance,
                lifetime_earned=account.lifetime_earned,
                lifetime_spent=account.lifetime_spent,
            )
        )
    return out


@store_credit_router.get(
    "/{seller_profile_id}/ledger", response_model=list[StoreCreditEntryRead]
)
async def get_store_credit_ledger(
    seller_profile_id: int,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> list[StoreCreditEntryRead]:
    profile_id = await _customer_profile_id(session, user)
    account = (
        await session.exec(
            select(CustomerStoreCredit).where(
                CustomerStoreCredit.seller_profile_id == seller_profile_id,
                CustomerStoreCredit.customer_profile_id == profile_id,
            )
        )
    ).first()
    # Another customer's account simply has no rows for this caller — never 403,
    # which would confirm the account exists.
    if account is None:
        return []
    entries = await store_credit_svc.list_entries(
        session, _pk(account.id), limit=limit, offset=offset
    )
    return [
        StoreCreditEntryRead(
            id=_pk(e.id), entry_type=e.entry_type.value, amount=e.amount,
            balance_after=e.balance_after, return_request_id=e.return_request_id,
            order_id=e.order_id, note=e.note, created_at=e.created_at,
        )
        for e in entries
    ]


# ─── Admin ───────────────────────────────────────────────────────────────


def _require_reason(reason: str) -> str:
    """Force paths need a real reason. Checked here rather than in the schema
    so the error uses the repo's `{"code": ...}` shape."""
    cleaned = (reason or "").strip()
    if len(cleaned) < 10:
        raise returns_svc.ReturnError(422, "reason_required")
    return cleaned


async def _load_return(
    session: AsyncSession, return_id: int, *, lock: bool = False
) -> ReturnRequest:
    request = (
        await returns_svc.lock_return(session, return_id)
        if lock
        else await session.get(ReturnRequest, return_id)
    )
    if request is None:
        raise returns_svc.ReturnError(404, "return_not_found")
    return request


async def _audit_return_action(
    session: AsyncSession,
    *,
    admin_user_id: int,
    request: ReturnRequest,
    action: str,
    before: dict[str, Any],
    reason: str,
) -> None:
    """Written in the SAME transaction as the mutation, so a rollback takes the
    audit row with it."""
    await audit_log(
        session=session,
        admin_user_id=admin_user_id,
        target_seller_id=request.seller_profile_id,
        target_type=AdminActionTargetType.Return,
        target_id=_pk(request.id),
        action=action,
        before_json=before,
        after_json={"status": request.status.value},
        reason=reason,
    )


@admin_router.get("/returns", response_model=list[ReturnRead])
async def admin_list_returns(
    seller_id: Optional[int] = Query(default=None),
    status_filter: Optional[ReturnStatus] = Query(default=None, alias="status"),
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[ReturnRead]:
    query = select(ReturnRequest)
    if seller_id is not None:
        query = query.where(ReturnRequest.seller_profile_id == seller_id)
    if status_filter is not None:
        query = query.where(ReturnRequest.status == status_filter)
    rows = list(
        (
            await session.exec(
                query.order_by(col(ReturnRequest.created_at).desc()).limit(200)
            )
        ).all()
    )
    return [_serialize(row, await _load_items(session, _pk(row.id))) for row in rows]


@admin_router.get("/sellers/{seller_id}/returns", response_model=list[ReturnRead])
async def admin_list_seller_returns(
    seller_id: int,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[ReturnRead]:
    """``seller_id`` is the seller's ``User.id``, matching every other
    /admin/sellers/{seller_id} route (and the hub's URL param)."""
    profile_id = (
        await session.exec(
            select(SellerProfile.id).where(SellerProfile.user_id == seller_id)
        )
    ).first()
    if profile_id is None:
        raise returns_svc.ReturnError(404, "seller_not_found")
    rows = list(
        (
            await session.exec(
                select(ReturnRequest)
                .where(ReturnRequest.seller_profile_id == int(profile_id))
                .order_by(col(ReturnRequest.created_at).desc())
                .limit(200)
            )
        ).all()
    )
    return [_serialize(row, await _load_items(session, _pk(row.id))) for row in rows]


@admin_router.get("/returns/{return_id}", response_model=ReturnRead)
async def admin_get_return(
    return_id: int,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnRead:
    request = await _load_return(session, return_id)
    return _serialize(request, await _load_items(session, return_id))


@admin_router.post("/returns", response_model=ReturnRead, status_code=201)
async def admin_create_return(
    body: ReturnCreateOnBehalfBody,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnRead:
    """Initiate on a customer's behalf. The customer's consent OTP is still
    mandatory — this lands in `awaiting_customer_confirmation` like any other.
    Force paths resolve stuck returns; they never manufacture consent."""
    order = await session.get(Order, body.order_id)
    if order is None or order.customer_profile_id != body.customer_profile_id:
        raise returns_svc.ReturnError(404, "order_not_found")
    version = await _require_agreement_version(session)
    request = await returns_svc.create_return(
        session, order=order, customer_profile_id=body.customer_profile_id,
        order_item_ids=body.order_item_ids, reason_code=body.reason_code,
        reason_note=body.reason_note, settlement_choice=body.settlement_choice,
        initiated_by=ReturnInitiator.admin, initiated_by_user_id=_pk(admin.id),
        agreement_version=version,
    )
    await session.commit()
    await session.refresh(request)
    owner_user_id = (
        await session.exec(
            select(CustomerProfile.user_id).where(
                CustomerProfile.id == body.customer_profile_id
            )
        )
    ).first()
    if owner_user_id is not None:
        await _send_initiation_otp(
            int(owner_user_id), _pk(request.id), best_effort=True
        )
    await _notify_return(session, request, "return_initiated")
    return _serialize(request, await _load_items(session, _pk(request.id)))


@admin_router.post("/returns/{return_id}/accept", response_model=ReturnRead)
async def admin_force_accept(
    return_id: int,
    body: AdminReturnAcceptBody,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnRead:
    request = await _load_return(session, return_id, lock=True)
    reason = _require_reason(body.reason)
    before = {"status": request.status.value}
    await returns_svc.accept_return(
        session, request, actor_role="admin", actor_user_id=_pk(admin.id),
        otp=None, restock=body.restock, bypass_otp=True,
        note=f"admin force accept: {reason}",
    )
    await _audit_return_action(
        session, admin_user_id=_pk(admin.id), request=request,
        action="return.force_accept", before=before, reason=reason,
    )
    await session.commit()
    await session.refresh(request)
    await _notify_return(session, request, "return_accepted")
    return _serialize(request, await _load_items(session, return_id))


@admin_router.post("/returns/{return_id}/reject", response_model=ReturnRead)
async def admin_force_reject(
    return_id: int,
    body: AdminReturnReasonBody,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnRead:
    request = await _load_return(session, return_id, lock=True)
    reason = _require_reason(body.reason)
    before = {"status": request.status.value}
    await returns_svc.reject_return(
        session, request, actor_role="admin", actor_user_id=_pk(admin.id),
        reason=reason,
    )
    await _audit_return_action(
        session, admin_user_id=_pk(admin.id), request=request,
        action="return.force_reject", before=before, reason=reason,
    )
    await session.commit()
    await session.refresh(request)
    await _notify_return(session, request, "return_rejected")
    return _serialize(request, await _load_items(session, return_id))


@admin_router.post("/returns/{return_id}/close", response_model=ReturnRead)
async def admin_force_close(
    return_id: int,
    body: AdminReturnReasonBody,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnRead:
    """Resolve a stuck return.

    From `awaiting_payment_confirmation` this closes it — the money moved
    outside the app and nobody confirmed. From the two earlier states nothing
    was ever settled, so it lands in `withdrawn` instead: marking those
    `closed` would record a completed return the customer never consented to,
    permanently lock the item lines (`closed` is line-locking) and count as a
    prior accepted return, blocking any retry on that order.
    """
    request = await _load_return(session, return_id, lock=True)
    reason = _require_reason(body.reason)
    if request.status == ReturnStatus.awaiting_payment_confirmation:
        target = ReturnStatus.closed
    elif request.status in (
        ReturnStatus.awaiting_customer_confirmation,
        ReturnStatus.active,
    ):
        target = ReturnStatus.withdrawn
    else:
        raise returns_svc.ReturnError(
            409, "illegal_return_transition",
            **{"from": request.status.value, "to": "closed"},
        )
    before = {"status": request.status.value}
    request.closed_at = datetime.now(timezone.utc)
    request.closed_by_user_id = _pk(admin.id)
    request.receipt_otp = None
    await returns_svc.record_transition(
        session, request, to_status=target,
        actor_role="admin", actor_user_id=_pk(admin.id),
        note=f"admin force close: {reason}",
    )
    await _audit_return_action(
        session, admin_user_id=_pk(admin.id), request=request,
        action="return.force_close", before=before, reason=reason,
    )
    await session.commit()
    await session.refresh(request)
    await _notify_return(session, request, "return_closed")
    return _serialize(request, await _load_items(session, return_id))


@admin_router.get(
    "/customers/{customer_profile_id}/store-credit",
    response_model=list[StoreCreditBalanceRead],
)
async def admin_customer_store_credit(
    customer_profile_id: int,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[StoreCreditBalanceRead]:
    """Read-only view of what sellers owe this customer. Sits beside the
    existing orders / addresses / notifications viewers on the customer hub."""
    accounts = await store_credit_svc.list_balances(session, customer_profile_id)
    out: list[StoreCreditBalanceRead] = []
    for account in accounts:
        store = (
            await session.exec(
                select(Store).where(
                    Store.seller_profile_id == account.seller_profile_id
                )
            )
        ).first()
        out.append(
            StoreCreditBalanceRead(
                seller_profile_id=account.seller_profile_id,
                store_id=store.id if store else None,
                store_name=store.name if store else "Store",
                balance=account.balance,
                lifetime_earned=account.lifetime_earned,
                lifetime_spent=account.lifetime_spent,
            )
        )
    return out
