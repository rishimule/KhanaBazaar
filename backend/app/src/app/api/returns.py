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

from fastapi import APIRouter, Depends
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
from app.core.security import get_current_customer
from app.db.session import get_db_session
from app.models.base import User
from app.models.commerce import Order
from app.models.consent import PolicyKind
from app.models.profile import CustomerProfile
from app.models.returns import (
    ReturnInitiator,
    ReturnRequest,
    ReturnRequestItem,
    ReturnStatus,
)
from app.schemas.returns import (
    ReturnConfirmBody,
    ReturnCreateBody,
    ReturnEligibilityLine,
    ReturnEligibilityRead,
    ReturnItemRead,
    ReturnRead,
)
from app.services import returns as returns_svc
from app.services.consent import get_current_version
from app.services.return_comms import dispatch_return_otp

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


async def _send_initiation_otp(user_id: int, return_id: int) -> None:
    redis = await get_redis()
    identifier = f"{user_id}:{return_id}"
    try:
        code = await request_otp(identifier, redis, namespace="return_initiate")
    except RateLimited as exc:
        raise returns_svc.ReturnError(
            429, "resend_cooldown", retry_after=exc.retry_after
        ) from exc
    dispatch_return_otp(user_id, return_id, code, "initiate")


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
    await _send_initiation_otp(_pk(user.id), _pk(request.id))
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
    session: AsyncSession, return_id: int, profile_id: int
) -> ReturnRequest:
    request = await session.get(ReturnRequest, return_id)
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
    request = await _owned_return(session, return_id, profile_id)
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
    request = await _owned_return(session, return_id, profile_id)
    await returns_svc.withdraw_return(session, request, actor_user_id=_pk(user.id))
    await session.commit()
    await session.refresh(request)
    return _serialize(request, await _load_items(session, return_id))
