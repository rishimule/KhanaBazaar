# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Courier order actions and read model (spec 2026-10-02 §9, §13).

Each action locks the order row, checks who may act and in which status,
mutates, commits, and returns the refreshed order. Messages are the caller's
job (api/orders.py) and run after the commit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.base import User, UserRole
from app.models.commerce import (
    DeliveryMode,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
)
from app.models.courier import CourierQuote, OrderCourier
from app.models.profile import SellerProfile
from app.models.store import Store
from app.schemas.orders import BankTransferRead, CourierQuoteRead, CourierRead
from app.services import customer_store_credit as store_credit_svc
from app.services.courier_rules import clean_text, eta_window, lock_order
from app.services.orders import _seller_owns_store
from app.services.serviceability import bank_transfer_live, courier_payment_methods
from app.utils.delivery_window import ist_today

Viewer = Literal["customer", "seller", "admin"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_courier(order: Order) -> None:
    if order.delivery_mode != DeliveryMode.Courier:
        raise HTTPException(status_code=409, detail={"code": "not_a_courier_order"})


async def _require_owning_seller(session: AsyncSession, actor: User, order: Order) -> None:
    """Quotes, payment confirmation, tracking and refunds are the store's own
    seller's actions — never an admin's (spec §9.7)."""
    if actor.role != UserRole.Seller or not await _seller_owns_store(
        session, actor, order.store_id
    ):
        raise HTTPException(status_code=403, detail="forbidden")


async def order_courier(session: AsyncSession, order_id: int) -> OrderCourier:
    row = (
        await session.exec(select(OrderCourier).where(OrderCourier.order_id == order_id))
    ).first()
    if row is None:
        raise HTTPException(status_code=500, detail="order_courier_missing")
    return row


async def latest_quote(session: AsyncSession, order_id: int) -> CourierQuote | None:
    return (
        await session.exec(
            select(CourierQuote)
            .where(CourierQuote.order_id == order_id)
            .order_by(col(CourierQuote.version).desc())
        )
    ).first()


async def store_seller(session: AsyncSession, store_id: int) -> SellerProfile:
    seller = (
        await session.exec(
            select(SellerProfile)
            .join(Store, Store.seller_profile_id == SellerProfile.id)  # type: ignore[arg-type]
            .where(Store.id == store_id)
        )
    ).first()
    if seller is None:
        raise HTTPException(status_code=500, detail="seller_missing")
    return seller


async def _payment(session: AsyncSession, order_id: int) -> Payment:
    payment = (await session.exec(select(Payment).where(Payment.order_id == order_id))).first()
    if payment is None:
        raise HTTPException(status_code=500, detail="order_missing_payment")
    return payment


async def send_quote(
    session: AsyncSession,
    order: Order,
    actor: User,
    *,
    courier_fee: float,
    eta_min_days: int,
    eta_max_days: int,
    carrier_name: str | None,
    note: str | None,
) -> tuple[Order, CourierQuote, bool]:
    """Insert the next quote version and move the order to `quoted`.
    Returns (order, quote, is_revision)."""
    _require_courier(order)
    await _require_owning_seller(session, actor, order)
    assert order.id is not None and actor.id is not None
    order = await lock_order(session, order.id)
    if order.status in (OrderStatus.Delivered, OrderStatus.Cancelled):
        raise HTTPException(status_code=409, detail={"code": "terminal_status"})
    if order.status not in (OrderStatus.Pending, OrderStatus.Quoted):
        raise HTTPException(status_code=409, detail={"code": "quote_locked"})
    previous = await latest_quote(session, order.id)
    version = (previous.version if previous else 0) + 1
    if version > settings.COURIER_MAX_QUOTE_VERSIONS:
        raise HTTPException(status_code=409, detail={"code": "too_many_quote_versions"})
    quote = CourierQuote(
        order_id=order.id,
        version=version,
        courier_fee=round(courier_fee, 2),
        eta_min_days=eta_min_days,
        eta_max_days=eta_max_days,
        carrier_name=clean_text(carrier_name, max_len=80),
        note=clean_text(note, max_len=300),
        created_by_user_id=actor.id,
    )
    session.add(quote)
    order.status = OrderStatus.Quoted
    session.add(order)
    await session.commit()
    await session.refresh(order)
    await session.refresh(quote)
    return order, quote, version > 1


async def build_courier_read(
    session: AsyncSession, order: Order, *, viewer: Viewer
) -> CourierRead | None:
    """The `courier` block of OrderRead; None for door/pickup orders."""
    if order.delivery_mode != DeliveryMode.Courier or order.id is None:
        return None
    row = (
        await session.exec(select(OrderCourier).where(OrderCourier.order_id == order.id))
    ).first()
    if row is None:
        return None
    quotes = list(
        (
            await session.exec(
                select(CourierQuote)
                .where(CourierQuote.order_id == order.id)
                .order_by(col(CourierQuote.version).desc())
            )
        ).all()
    )
    visible = quotes if viewer != "customer" else quotes[:1]
    payment = (await session.exec(select(Payment).where(Payment.order_id == order.id))).first()
    seller = (
        await session.exec(
            select(SellerProfile)
            .join(Store, Store.seller_profile_id == SellerProfile.id)  # type: ignore[arg-type]
            .where(Store.id == order.store_id)
        )
    ).first()
    bank: BankTransferRead | None = None
    if (
        viewer == "customer"
        and order.status == OrderStatus.Accepted
        and seller is not None
        and bank_transfer_live(seller)
    ):
        bank = BankTransferRead(
            account_name=seller.bank_account_name or "",
            account_number=seller.bank_account_number or "",
            ifsc=seller.bank_ifsc or "",
        )
    return CourierRead(
        recipient_name=row.recipient_name,
        recipient_phone=row.recipient_phone,
        quotes=[
            CourierQuoteRead(
                id=q.id or 0,
                version=q.version,
                courier_fee=q.courier_fee,
                eta_min_days=q.eta_min_days,
                eta_max_days=q.eta_max_days,
                carrier_name=q.carrier_name,
                note=q.note,
                created_at=q.created_at,
            )
            for q in visible
        ],
        revised=bool(quotes) and quotes[0].version > 1,
        accepted_quote_id=row.accepted_quote_id,
        accepted_at=row.accepted_at,
        eta_from=row.eta_from,
        eta_to=row.eta_to,
        payment_claim_rejected_at=row.payment_claim_rejected_at,
        payment_claim_rejected_note=row.payment_claim_rejected_note,
        carrier_name=row.carrier_name,
        tracking_number=row.tracking_number,
        tracking_url=row.tracking_url,
        tracking_updated_at=row.tracking_updated_at,
        delivered_by=row.delivered_by,
        cancel_reason=row.cancel_reason,
        cancelled_by=row.cancelled_by,
        cancelled_at=row.cancelled_at,
        payment_reported_missing_at=row.payment_reported_missing_at,
        refund_due=(
            order.status == OrderStatus.Cancelled
            and payment is not None
            and payment.status == PaymentStatus.Paid
        ),
        payable_methods=courier_payment_methods(seller) if seller is not None else [],
        bank_transfer=bank,
    )


class CourierPayeeMissing(Exception):
    """The seller has no live prepaid payee, so the customer could not pay."""


@dataclass(frozen=True)
class AcceptResult:
    order: Order
    auto_paid: bool
    already_accepted: bool


async def accept_quote(
    session: AsyncSession, order: Order, actor: User, *, quote_id: int
) -> AcceptResult:
    """Lock in the latest quote: the charge becomes the delivery fee, totals
    are recalculated, store credit tops up, and ₹0 payable goes straight to
    `paid` (spec §9.4, §10.1)."""
    _require_courier(order)
    if actor.role != UserRole.Customer:
        raise HTTPException(status_code=403, detail="forbidden")
    assert order.id is not None
    order = await lock_order(session, order.id)
    row = await order_courier(session, order.id)
    if row.accepted_quote_id == quote_id and order.status in (
        OrderStatus.Accepted, OrderStatus.Paid,
    ):
        return AcceptResult(order=order, auto_paid=False, already_accepted=True)
    if order.status != OrderStatus.Quoted:
        raise HTTPException(status_code=409, detail={"code": "illegal_transition"})
    latest = await latest_quote(session, order.id)
    if latest is None or latest.id != quote_id:
        raise HTTPException(status_code=409, detail={"code": "quote_superseded"})
    seller = await store_seller(session, order.store_id)
    if not courier_payment_methods(seller):
        raise CourierPayeeMissing()
    payment = await _payment(session, order.id)
    now = _now()

    order.delivery_fee = round(latest.courier_fee, 2)
    order.total = round(order.subtotal + order.delivery_fee + order.tax, 2)
    if row.apply_store_credit:
        remaining = round(order.total - order.store_credit_applied, 2)
        if remaining > 0:
            account = await store_credit_svc.lock_account(
                session,
                seller_profile_id=seller.id or 0,
                customer_profile_id=order.customer_profile_id,
            )
            if account is not None and account.balance > 0:
                applied = await store_credit_svc.spend(
                    session,
                    account,
                    min(account.balance, remaining),
                    order_id=order.id,
                    actor_user_id=actor.id,
                )
                order.store_credit_applied = round(order.store_credit_applied + applied, 2)
    payment.amount = round(order.total - order.store_credit_applied, 2)
    row.accepted_quote_id = latest.id
    row.accepted_at = now

    auto_paid = payment.amount <= 0
    if auto_paid:
        # No money moves, so no seller confirmation is needed.
        payment.amount = 0.0
        payment.status = PaymentStatus.Paid
        payment.paid_at = now
        order.status = OrderStatus.Paid
        row.eta_from, row.eta_to = eta_window(
            latest.eta_min_days, latest.eta_max_days, today=ist_today()
        )
    else:
        order.status = OrderStatus.Accepted
    session.add_all([order, payment, row])
    await session.commit()
    await session.refresh(order)
    return AcceptResult(order=order, auto_paid=auto_paid, already_accepted=False)
