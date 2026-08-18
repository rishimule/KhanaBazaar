# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Return-order service: eligibility, amount computation, and the state machine.

Services flush; callers commit. Every status change goes through
``record_transition`` so ``return_event`` never drifts from ``return_request``.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Delivery, Order, OrderItem, OrderStatus
from app.models.profile import SellerProfileService
from app.models.returns import (
    ACCEPTED_RETURN_STATUSES,
    LINE_LOCKING_STATUSES,
    ReturnEvent,
    ReturnRequest,
    ReturnRequestItem,
    ReturnStatus,
)
from app.models.store import Store


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
