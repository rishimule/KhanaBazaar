# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Return-order service: eligibility, amount computation, and the state machine.

Services flush; callers commit. Every status change goes through
``record_transition`` so ``return_event`` never drifts from ``return_request``.
"""
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from fastapi import HTTPException
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.otp import generate_code
from app.models.base import User
from app.models.commerce import Delivery, Order, OrderItem, OrderStatus
from app.models.profile import SellerProfile, SellerProfileService
from app.models.returns import (
    ACCEPTED_RETURN_STATUSES,
    LINE_LOCKING_STATUSES,
    ReturnEvent,
    ReturnInitiator,
    ReturnReasonCode,
    ReturnRequest,
    ReturnRequestItem,
    ReturnSettlementChoice,
    ReturnStatus,
)
from app.models.store import Store, StoreInventory

if TYPE_CHECKING:  # avoids a cycle: return_settlement imports this module
    from app.services.return_settlement import SettlementResult


def _pk(value: Optional[int]) -> int:
    """Narrow a persisted row's primary key. Any row read back from the DB has
    one; BaseSchema types it Optional only because it is None pre-flush."""
    assert value is not None
    return value


class ReturnError(HTTPException):
    """Domain error carrying the repo's ``{"code": ...}`` detail shape."""

    def __init__(self, status_code: int, code: str, **extra: object) -> None:
        super().__init__(status_code=status_code, detail={"code": code, **extra})


@dataclass
class LineEligibility:
    order_item_id: int
    product_name: str
    unit_price: float
    quantity: int
    line_total: float
    returnable: bool
    lock_reason: Optional[str]


@dataclass
class EligibilityResult:
    eligible: bool
    reason_code: Optional[str]
    window_expires_at: Optional[datetime]
    delivery_fee: float
    full_order_available: bool
    lines: list[LineEligibility]


async def resolve_seller_profile_id(session: AsyncSession, store_id: int) -> int:
    seller_id = (
        await session.exec(select(Store.seller_profile_id).where(Store.id == store_id))
    ).first()
    if seller_id is None:
        raise ReturnError(404, "store_not_found")
    return int(seller_id)


async def load_service_config(
    session: AsyncSession, *, seller_profile_id: int, service_id: int
) -> Optional[SellerProfileService]:
    return (
        await session.exec(
            select(SellerProfileService).where(
                SellerProfileService.seller_profile_id == seller_profile_id,
                SellerProfileService.service_id == service_id,
            )
        )
    ).first()


async def locked_order_item_ids(session: AsyncSession, order_id: int) -> set[int]:
    """Order lines held by a return that has not released them."""
    rows = await session.exec(
        select(ReturnRequestItem.order_item_id)
        .join(
            ReturnRequest,
            col(ReturnRequest.id) == ReturnRequestItem.return_request_id,
        )
        .where(
            ReturnRequest.order_id == order_id,
            col(ReturnRequest.status).in_(LINE_LOCKING_STATUSES),
        )
    )
    return {int(r) for r in rows.all()}


async def has_accepted_return(session: AsyncSession, order_id: int) -> bool:
    """True when the seller already took receipt of a return on this order."""
    row = await session.exec(
        select(ReturnRequest.id).where(
            ReturnRequest.order_id == order_id,
            col(ReturnRequest.status).in_(ACCEPTED_RETURN_STATUSES),
        )
    )
    return row.first() is not None


async def compute_eligibility(
    session: AsyncSession, *, order: Order, customer_profile_id: int
) -> EligibilityResult:
    """Never raises for an ineligible order — it reports why, so the UI can
    explain. Ownership is enforced by the caller, not here."""
    items = list(
        (
            await session.exec(
                select(OrderItem)
                .where(OrderItem.order_id == order.id)
                .order_by(col(OrderItem.id))
            )
        ).all()
    )

    def _blank(reason: str) -> EligibilityResult:
        return EligibilityResult(
            eligible=False, reason_code=reason, window_expires_at=None,
            delivery_fee=order.delivery_fee, full_order_available=False,
            lines=[
                LineEligibility(
                    order_item_id=_pk(i.id), product_name=i.product_name_snapshot,
                    unit_price=i.unit_price_snapshot, quantity=i.quantity,
                    line_total=i.line_total, returnable=False, lock_reason=reason,
                )
                for i in items
            ],
        )

    if order.status != OrderStatus.Delivered:
        return _blank("order_not_delivered")

    delivery = (
        await session.exec(select(Delivery).where(Delivery.order_id == order.id))
    ).first()
    if delivery is None or delivery.delivered_at is None:
        return _blank("order_not_delivered")

    seller_profile_id = await resolve_seller_profile_id(session, order.store_id)
    config = await load_service_config(
        session, seller_profile_id=seller_profile_id, service_id=order.service_id
    )
    if config is None or config.return_window_days <= 0:
        return _blank("returns_disabled_for_service")

    window_expires_at = delivery.delivered_at + timedelta(days=config.return_window_days)
    if datetime.now(timezone.utc) > window_expires_at:
        result = _blank("return_window_closed")
        result.window_expires_at = window_expires_at
        return result

    locked = await locked_order_item_ids(session, _pk(order.id))
    lines = [
        LineEligibility(
            order_item_id=_pk(i.id), product_name=i.product_name_snapshot,
            unit_price=i.unit_price_snapshot, quantity=i.quantity,
            line_total=i.line_total, returnable=_pk(i.id) not in locked,
            lock_reason="already_in_return" if _pk(i.id) in locked else None,
        )
        for i in items
    ]
    any_returnable = any(line.returnable for line in lines)
    prior_accepted = await has_accepted_return(session, _pk(order.id))
    return EligibilityResult(
        eligible=any_returnable,
        reason_code=None if any_returnable else "items_already_returned",
        window_expires_at=window_expires_at,
        delivery_fee=order.delivery_fee,
        full_order_available=(
            bool(lines) and all(line.returnable for line in lines) and not prior_accepted
        ),
        lines=lines,
    )


def compute_amounts(
    line_totals: list[float], *, is_full_order: bool, delivery_fee: float
) -> tuple[float, float, float]:
    """Return (items_amount, delivery_fee_amount, total_amount).

    The delivery fee comes back only on a full-order return (spec §7.1) — the
    caller decides ``is_full_order``; this does the arithmetic only.
    """
    items_amount = round(sum(line_totals), 2)
    fee = round(delivery_fee, 2) if is_full_order else 0.0
    return items_amount, fee, round(items_amount + fee, 2)


async def record_transition(
    session: AsyncSession,
    request: ReturnRequest,
    *,
    to_status: ReturnStatus,
    actor_role: str,
    actor_user_id: Optional[int],
    note: Optional[str] = None,
) -> ReturnEvent:
    """Move the request and log the move. Flushes; the caller commits."""
    event = ReturnEvent(
        return_request_id=request.id, from_status=request.status, to_status=to_status,
        actor_role=actor_role, actor_user_id=actor_user_id, note=note,
    )
    request.status = to_status
    session.add(request)
    session.add(event)
    await session.flush()
    return event


async def create_return(
    session: AsyncSession,
    *,
    order: Order,
    customer_profile_id: int,
    order_item_ids: list[int],
    reason_code: ReturnReasonCode,
    reason_note: Optional[str],
    settlement_choice: ReturnSettlementChoice,
    initiated_by: ReturnInitiator,
    initiated_by_user_id: int,
    agreement_version: int,
) -> ReturnRequest:
    """Create a return in `awaiting_customer_confirmation`. Flushes; caller commits.

    The order row is locked for the duration so two concurrent requests cannot
    both claim the same line — the only race that matters here.
    """
    if not order_item_ids:
        raise ReturnError(422, "no_items_selected")
    if reason_code == ReturnReasonCode.other and not (reason_note or "").strip():
        raise ReturnError(422, "reason_note_required")

    # Serialise concurrent creation on this order.
    await session.exec(select(Order).where(Order.id == order.id).with_for_update())

    result = await compute_eligibility(
        session, order=order, customer_profile_id=customer_profile_id
    )
    if not result.eligible:
        raise ReturnError(409, result.reason_code or "not_eligible")

    by_id = {line.order_item_id: line for line in result.lines}
    selected = list(dict.fromkeys(order_item_ids))  # de-dupe, preserve order
    for item_id in selected:
        if item_id not in by_id:
            raise ReturnError(422, "invalid_order_item", order_item_id=item_id)
        if not by_id[item_id].returnable:
            raise ReturnError(409, "items_already_returned", order_item_id=item_id)

    is_full_order = result.full_order_available and len(selected) == len(result.lines)
    items_amount, fee_amount, total_amount = compute_amounts(
        [by_id[i].line_total for i in selected],
        is_full_order=is_full_order,
        delivery_fee=order.delivery_fee,
    )

    now = datetime.now(timezone.utc)
    request = ReturnRequest(
        order_id=_pk(order.id),
        customer_profile_id=customer_profile_id,
        store_id=order.store_id,
        seller_profile_id=await resolve_seller_profile_id(session, order.store_id),
        service_id=order.service_id,
        initiated_by=initiated_by,
        initiated_by_user_id=initiated_by_user_id,
        status=ReturnStatus.awaiting_customer_confirmation,
        is_full_order=is_full_order,
        reason_code=reason_code,
        reason_note=(reason_note or "").strip() or None,
        items_amount=items_amount,
        delivery_fee_amount=fee_amount,
        total_amount=total_amount,
        settlement_choice=settlement_choice,
        agreement_policy_version=agreement_version,
        window_expires_at=result.window_expires_at or now,
        confirm_expires_at=now + timedelta(hours=settings.RETURN_CONFIRM_HOURS),
    )
    session.add(request)
    await session.flush()

    for item_id in selected:
        line = by_id[item_id]
        session.add(
            ReturnRequestItem(
                return_request_id=request.id,
                order_item_id=item_id,
                quantity=line.quantity,
                product_name_snapshot=line.product_name,
                unit_price_snapshot=line.unit_price,
                line_total=line.line_total,
            )
        )

    session.add(
        ReturnEvent(
            return_request_id=request.id,
            from_status=None,
            to_status=ReturnStatus.awaiting_customer_confirmation,
            actor_role=initiated_by.value,
            actor_user_id=initiated_by_user_id,
            note=None,
        )
    )
    await session.flush()
    return request


async def confirm_return(
    session: AsyncSession, request: ReturnRequest, *, actor_user_id: int
) -> ReturnRequest:
    """Activate a confirmed return and issue the handover code the seller will
    type. Flushes; caller commits.

    The receipt code lives on the row rather than in Redis because it must
    survive until the customer physically reaches the store — days, not the
    ten minutes a Redis OTP lasts.
    """
    if request.status != ReturnStatus.awaiting_customer_confirmation:
        raise ReturnError(
            409, "illegal_return_transition",
            **{"from": request.status.value, "to": ReturnStatus.active.value},
        )
    now = datetime.now(timezone.utc)
    if now > request.confirm_expires_at:
        raise ReturnError(409, "confirmation_expired")

    request.agreement_accepted_at = now
    request.confirmed_at = now
    request.handover_expires_at = now + timedelta(days=settings.RETURN_HANDOVER_DAYS)
    request.receipt_otp = generate_code()
    request.receipt_otp_attempts = 0
    request.receipt_otp_sent_at = now
    request.receipt_otp_verified_at = None
    await record_transition(
        session, request, to_status=ReturnStatus.active,
        actor_role="customer", actor_user_id=actor_user_id,
        note="initiation otp confirmed",
    )
    return request


async def withdraw_return(
    session: AsyncSession,
    request: ReturnRequest,
    *,
    actor_user_id: int,
    actor_role: str = "customer",
    note: Optional[str] = None,
) -> ReturnRequest:
    """Customer pulls out before handover. Releases the item lines. Flushes.

    Covers both "withdrew my own request" and "refused one the seller started";
    `return_event.from_status` distinguishes them without a second enum member.
    """
    if request.status not in (
        ReturnStatus.awaiting_customer_confirmation,
        ReturnStatus.active,
    ):
        raise ReturnError(
            409, "illegal_return_transition",
            **{"from": request.status.value, "to": ReturnStatus.withdrawn.value},
        )
    request.receipt_otp = None
    request.closed_at = datetime.now(timezone.utc)
    request.closed_by_user_id = actor_user_id
    await record_transition(
        session, request, to_status=ReturnStatus.withdrawn,
        actor_role=actor_role, actor_user_id=actor_user_id, note=note,
    )
    return request


async def seller_owns_return(
    session: AsyncSession, user: User, request: ReturnRequest
) -> bool:
    profile_id = (
        await session.exec(
            select(SellerProfile.id).where(SellerProfile.user_id == user.id)
        )
    ).first()
    return profile_id is not None and int(profile_id) == request.seller_profile_id


async def restock_items(session: AsyncSession, request: ReturnRequest) -> None:
    """Add returned quantities back to sellable stock.

    Lines whose `inventory_id` is NULL (product de-listed since the order) are
    skipped — there is no row to credit, and inventing one would be worse than
    leaving the seller to adjust by hand.
    """
    rows = await session.exec(
        select(ReturnRequestItem, OrderItem)
        .join(OrderItem, col(OrderItem.id) == ReturnRequestItem.order_item_id)
        .where(ReturnRequestItem.return_request_id == request.id)
    )
    for return_item, order_item in rows.all():
        if order_item.inventory_id is None:
            continue
        inventory = (
            await session.exec(
                select(StoreInventory)
                .where(StoreInventory.id == order_item.inventory_id)
                .with_for_update()
            )
        ).first()
        if inventory is None:
            continue
        inventory.stock += return_item.quantity
        session.add(inventory)
    await session.flush()


async def verify_receipt_otp(
    session: AsyncSession, request: ReturnRequest, otp: Optional[str]
) -> None:
    """Handover-code gate, adapted from the delivery-OTP gate in
    services/orders.py. Runs BEFORE any status mutation so a failed
    verification never persists an accepted return."""
    if request.receipt_otp is None:
        raise ReturnError(409, "receipt_otp_not_issued")
    if request.receipt_otp_attempts >= settings.RETURN_OTP_MAX_ATTEMPTS:
        raise ReturnError(409, "receipt_otp_locked")
    if not otp:
        raise ReturnError(422, "receipt_otp_required")
    # `otp.isascii()` short-circuits before compare_digest, which raises
    # TypeError on non-ASCII str input — a non-ASCII code counts as a wrong
    # attempt (no 500, no counter bypass).
    if not (otp.isascii() and hmac.compare_digest(otp, request.receipt_otp)):
        request.receipt_otp_attempts += 1
        session.add(request)
        # Capture before commit() expires the instance (reading the attribute
        # afterwards would trigger a lazy load → MissingGreenlet).
        attempts_now = request.receipt_otp_attempts
        await session.commit()  # persist the failed attempt; status untouched
        raise ReturnError(
            422, "receipt_otp_invalid",
            remaining=max(0, settings.RETURN_OTP_MAX_ATTEMPTS - attempts_now),
        )


async def accept_return(
    session: AsyncSession,
    request: ReturnRequest,
    *,
    actor_role: str,
    actor_user_id: int,
    otp: Optional[str],
    restock: bool,
    bypass_otp: bool = False,
    note: Optional[str] = None,
) -> "SettlementResult":
    """Seller (or admin, with `bypass_otp`) takes receipt and settles."""
    from app.services.return_settlement import settle

    if request.status != ReturnStatus.active:
        raise ReturnError(
            409, "illegal_return_transition",
            **{"from": request.status.value, "to": "accepted"},
        )
    if not bypass_otp:
        await verify_receipt_otp(session, request, otp)

    now = datetime.now(timezone.utc)
    request.restock = restock
    request.decided_at = now
    request.decided_by_user_id = actor_user_id
    if not bypass_otp:
        request.receipt_otp_verified_at = now
    request.receipt_otp = None  # consume the code

    result = await settle(session, request, actor_user_id=actor_user_id)
    if restock:
        await restock_items(session, request)

    if result.next_status == ReturnStatus.closed:
        request.closed_at = now
        request.closed_by_user_id = actor_user_id
    await record_transition(
        session, request, to_status=result.next_status,
        actor_role=actor_role, actor_user_id=actor_user_id,
        note=note or "receipt otp confirmed",
    )
    return result


async def reject_return(
    session: AsyncSession,
    request: ReturnRequest,
    *,
    actor_role: str,
    actor_user_id: int,
    reason: str,
) -> ReturnRequest:
    """Seller refuses the return. Terminal; the two parties settle off-platform
    and the application records only the status and the reason (BRD §7)."""
    if request.status != ReturnStatus.active:
        raise ReturnError(
            409, "illegal_return_transition",
            **{"from": request.status.value, "to": ReturnStatus.rejected.value},
        )
    cleaned = (reason or "").strip()
    if not cleaned:
        raise ReturnError(422, "reason_required")
    now = datetime.now(timezone.utc)
    request.rejection_reason = cleaned
    request.receipt_otp = None
    request.decided_at = now
    request.decided_by_user_id = actor_user_id
    request.closed_at = now
    request.closed_by_user_id = actor_user_id
    await record_transition(
        session, request, to_status=ReturnStatus.rejected,
        actor_role=actor_role, actor_user_id=actor_user_id, note=cleaned,
    )
    return request


async def close_after_payment(
    session: AsyncSession, request: ReturnRequest, *, actor_user_id: int
) -> ReturnRequest:
    """Customer confirms the money reached them. The platform validates nothing
    about the transfer itself — this records the confirmation (spec §2)."""
    if request.status != ReturnStatus.awaiting_payment_confirmation:
        raise ReturnError(
            409, "illegal_return_transition",
            **{"from": request.status.value, "to": ReturnStatus.closed.value},
        )
    now = datetime.now(timezone.utc)
    request.closed_at = now
    request.closed_by_user_id = actor_user_id
    await record_transition(
        session, request, to_status=ReturnStatus.closed,
        actor_role="customer", actor_user_id=actor_user_id,
        note="payment receipt otp confirmed",
    )
    return request
