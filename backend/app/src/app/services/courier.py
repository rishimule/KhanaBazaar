# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Courier order actions and read model (spec 2026-10-02 §9, §13).

Each action locks the order row, checks who may act and in which status,
mutates, commits, and returns the refreshed order. Messages are the caller's
job (api/orders.py) and run after the commit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy import select as sa_select
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.base import User, UserRole
from app.models.commerce import (
    Delivery,
    DeliveryMode,
    DeliveryStatus,
    Order,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from app.models.courier import CourierQuote, OrderCourier
from app.models.profile import SellerProfile
from app.models.store import Store
from app.schemas.orders import BankTransferRead, CourierQuoteRead, CourierRead
from app.services import customer_store_credit as store_credit_svc
from app.services.courier_rules import (
    TrackingInput,
    apply_tracking,
    clean_text,
    eta_window,
    lock_order,
    refund_owed,
    validate_tracking_url,
)
from app.services.orders import _seller_owns_store
from app.services.payment_methods import effective_bank
from app.services.receipts import issue_in_savepoint as issue_receipt_in_savepoint
from app.services.serviceability import courier_payment_methods
from app.utils.delivery_window import ist_today

Viewer = Literal["customer", "seller", "admin"]

# An identical quote this soon after the last one is a double tap or a retried
# request, not a revision.
QUOTE_RETRY_WINDOW = timedelta(seconds=60)


@dataclass(frozen=True)
class QuoteResult:
    order: Order
    quote: CourierQuote
    revised: bool
    # True when the request repeated the latest quote seconds later: nothing
    # was written, so nobody should be told anything.
    duplicate: bool = False


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
) -> QuoteResult:
    """Insert the next quote version and move the order to `quoted`."""
    _require_courier(order)
    await _require_owning_seller(session, actor, order)
    assert order.id is not None and actor.id is not None
    order_id: int = order.id
    order = await lock_order(session, order_id)
    if order.status in (OrderStatus.Delivered, OrderStatus.Cancelled):
        raise HTTPException(status_code=409, detail={"code": "terminal_status"})
    if order.status not in (OrderStatus.Pending, OrderStatus.Quoted):
        raise HTTPException(status_code=409, detail={"code": "quote_locked"})
    previous = await latest_quote(session, order_id)
    fee = round(courier_fee, 2)
    carrier = clean_text(carrier_name, max_len=80)
    cleaned_note = clean_text(note, max_len=300)
    if (
        previous is not None
        and order.status == OrderStatus.Quoted
        and (previous.courier_fee, previous.eta_min_days, previous.eta_max_days)
        == (fee, eta_min_days, eta_max_days)
        and (previous.carrier_name, previous.note) == (carrier, cleaned_note)
        and _now() - previous.created_at < QUOTE_RETRY_WINDOW
    ):
        # Don't burn a version, tell the customer it was "updated", or make a
        # customer accepting the first copy hit quote_superseded.
        revised = previous.version > 1  # read before commit expires it
        await session.commit()  # release the row lock; nothing changed
        await session.refresh(order)
        return QuoteResult(order, previous, revised=revised, duplicate=True)
    version = (previous.version if previous else 0) + 1
    if version > settings.COURIER_MAX_QUOTE_VERSIONS:
        raise HTTPException(status_code=409, detail={"code": "too_many_quote_versions"})
    quote = CourierQuote(
        order_id=order_id,
        version=version,
        courier_fee=fee,
        eta_min_days=eta_min_days,
        eta_max_days=eta_max_days,
        carrier_name=carrier,
        note=cleaned_note,
        created_by_user_id=actor.id,
    )
    session.add(quote)
    order.status = OrderStatus.Quoted
    session.add(order)
    await session.commit()
    await session.refresh(order)
    await session.refresh(quote)
    return QuoteResult(order, quote, revised=version > 1)


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
    if viewer == "customer" and order.status == OrderStatus.Accepted and seller is not None:
        # Same rule as OrderRead.payee: the saved copy unless switched off since
        # (spec 2026-10-07 §7). Kept here for clients older than `payee`.
        payee = effective_bank(payment, seller)
        if payee is not None:
            bank = BankTransferRead(
                account_name=payee.account_name,
                account_number=payee.account_number,
                ifsc=payee.ifsc,
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
        max_quote_versions=settings.COURIER_MAX_QUOTE_VERSIONS,
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
            payment is not None
            and refund_owed(order.status, payment.status, payment.amount)
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
    order_id: int = order.id
    order = await lock_order(session, order_id)
    row = await order_courier(session, order_id)
    if row.accepted_quote_id == quote_id and order.status in (
        OrderStatus.Accepted, OrderStatus.Paid,
    ):
        return AcceptResult(order=order, auto_paid=False, already_accepted=True)
    if order.status != OrderStatus.Quoted:
        raise HTTPException(status_code=409, detail={"code": "illegal_transition"})
    latest = await latest_quote(session, order_id)
    if latest is None or latest.id != quote_id:
        raise HTTPException(status_code=409, detail={"code": "quote_superseded"})
    seller = await store_seller(session, order.store_id)
    if not courier_payment_methods(seller):
        raise CourierPayeeMissing()
    payment = await _payment(session, order_id)
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
                    order_id=order_id,
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


_COURIER_METHODS = (PaymentMethod.Upi, PaymentMethod.NetBanking)


async def claim_payment(
    session: AsyncSession, order: Order, actor: User, *, method: PaymentMethod | None
) -> tuple[Order, bool]:
    """The customer's "I've paid", recording which method they used. A repeat
    keeps the first timestamp. Returns (order, newly_claimed)."""
    _require_courier(order)
    assert order.id is not None
    order_id: int = order.id
    order = await lock_order(session, order_id)
    payment = await _payment(session, order_id)
    if order.status != OrderStatus.Accepted:
        raise HTTPException(status_code=409, detail="not_awaiting_payment")
    if payment.status is not PaymentStatus.Pending:
        raise HTTPException(status_code=409, detail="payment_settled")
    if method is None:
        raise HTTPException(status_code=422, detail="payment_method_required")
    if method not in _COURIER_METHODS:
        raise HTTPException(status_code=422, detail="payment_method_not_allowed")
    seller = await store_seller(session, order.store_id)
    live = courier_payment_methods(seller)
    if not live:
        # Every payee is gone: the route tells the seller (spec §9.9).
        raise CourierPayeeMissing()
    if method not in live:
        raise HTTPException(
            status_code=409,
            detail="upi_unavailable" if method is PaymentMethod.Upi else "bank_transfer_unavailable",
        )
    row = await order_courier(session, order_id)
    # One seller message per claim round; switching method is recorded silently
    # (the seller's screen shows the current method).
    newly_claimed = payment.customer_claimed_at is None
    payment.method = method
    if payment.customer_claimed_at is None:
        payment.customer_claimed_at = _now()
    row.payment_claim_rejected_at = None
    row.payment_claim_rejected_note = None
    session.add_all([payment, row])
    await session.commit()
    await session.refresh(order)
    return order, newly_claimed


async def confirm_payment(session: AsyncSession, order: Order, actor: User) -> Order:
    """The seller's "Payment received": Paid now, delivery dates fixed now."""
    _require_courier(order)
    await _require_owning_seller(session, actor, order)
    assert order.id is not None
    order_id: int = order.id
    order = await lock_order(session, order_id)
    payment = await _payment(session, order_id)
    if payment.status is PaymentStatus.Paid or order.status is OrderStatus.Paid:
        raise HTTPException(status_code=409, detail={"code": "payment_settled"})
    if order.status != OrderStatus.Accepted:
        raise HTTPException(status_code=409, detail={"code": "illegal_transition"})
    row = await order_courier(session, order_id)
    quote = await session.get(CourierQuote, row.accepted_quote_id) if row.accepted_quote_id else None
    if quote is None:
        raise HTTPException(status_code=500, detail="accepted_quote_missing")
    now = _now()
    payment.status = PaymentStatus.Paid
    payment.paid_at = now
    order.status = OrderStatus.Paid
    row.eta_from, row.eta_to = eta_window(quote.eta_min_days, quote.eta_max_days, today=ist_today())
    session.add_all([order, payment, row])
    await session.commit()
    await session.refresh(order)
    return order


async def reject_payment_claim(
    session: AsyncSession, order: Order, actor: User, *, note: str | None
) -> Order:
    """The seller's "Payment not received": clears the claim so the customer
    can check and pay again; the note is shown to them."""
    _require_courier(order)
    await _require_owning_seller(session, actor, order)
    assert order.id is not None
    order_id: int = order.id
    order = await lock_order(session, order_id)
    if order.status != OrderStatus.Accepted:
        raise HTTPException(status_code=409, detail={"code": "illegal_transition"})
    payment = await _payment(session, order_id)
    if payment.customer_claimed_at is None:
        raise HTTPException(status_code=409, detail={"code": "no_claim"})
    row = await order_courier(session, order_id)
    payment.customer_claimed_at = None
    row.payment_claim_rejected_at = _now()
    row.payment_claim_rejected_note = clean_text(note, max_len=300)
    row.payment_claim_rejection_count += 1
    session.add_all([payment, row])
    await session.commit()
    await session.refresh(order)
    return order


async def update_tracking(
    session: AsyncSession, order: Order, actor: User, tracking: TrackingInput
) -> tuple[Order, bool]:
    """Edit tracking after shipping. Returns (order, changed)."""
    _require_courier(order)
    await _require_owning_seller(session, actor, order)
    assert order.id is not None
    order_id: int = order.id
    order = await lock_order(session, order_id)
    if order.status != OrderStatus.Dispatched:
        raise HTTPException(status_code=409, detail={"code": "not_dispatched"})
    try:
        validate_tracking_url(tracking.tracking_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_tracking_url"}) from exc
    row = await order_courier(session, order_id)
    changed = apply_tracking(row, tracking)
    if changed:
        row.tracking_updated_at = _now()
        session.add(row)
        await session.commit()
    await session.refresh(order)
    return order, changed


async def mark_received(session: AsyncSession, order: Order, actor: User) -> Order:
    """The customer's "I've received it" (spec D9)."""
    _require_courier(order)
    if actor.role != UserRole.Customer:
        raise HTTPException(status_code=403, detail="forbidden")
    assert order.id is not None
    order_id: int = order.id
    order = await lock_order(session, order_id)
    if order.status == OrderStatus.Delivered:
        raise HTTPException(status_code=409, detail={"code": "already_delivered"})
    if order.status != OrderStatus.Dispatched:
        raise HTTPException(status_code=409, detail={"code": "illegal_transition"})
    delivery = (await session.exec(select(Delivery).where(Delivery.order_id == order_id))).first()
    if delivery is None:
        raise HTTPException(status_code=500, detail="delivery_missing")
    row = await order_courier(session, order_id)
    now = _now()
    order.status = OrderStatus.Delivered
    delivery.status = DeliveryStatus.Delivered
    delivery.delivered_at = now
    row.delivered_by = "customer"
    session.add_all([order, delivery, row])
    await issue_receipt_in_savepoint(session, order, delivered_at=now)
    await session.commit()
    await session.refresh(order)
    return order


async def mark_refund_sent(
    session: AsyncSession, order: Order, actor: User, *, reference: str | None
) -> Order:
    """The seller's "Refund sent" on a cancelled, paid courier order (§10.3)."""
    _require_courier(order)
    await _require_owning_seller(session, actor, order)
    assert order.id is not None
    order_id: int = order.id
    order = await lock_order(session, order_id)
    payment = await _payment(session, order_id)
    if payment.status is PaymentStatus.Refunded:
        raise HTTPException(status_code=409, detail={"code": "already_refunded"})
    if not refund_owed(order.status, payment.status, payment.amount):
        raise HTTPException(status_code=409, detail={"code": "refund_not_due"})
    payment.status = PaymentStatus.Refunded
    payment.refunded_at = _now()
    payment.refund_reference = clean_text(reference, max_len=60)
    payment.refunded_by_user_id = actor.id
    session.add(payment)
    await session.commit()
    await session.refresh(order)
    return order


def stale_courier_clause(now: datetime, today: date) -> ColumnElement[bool]:
    """Courier orders whose current stage is older than COURIER_STALE_DAYS, or
    shipped and past eta_to + grace — the admin backstop once reminders are
    spent (spec §11.2)."""
    cutoff = now - timedelta(days=settings.COURIER_STALE_DAYS)
    overdue_before = today - timedelta(days=settings.COURIER_ARRIVAL_GRACE_DAYS)
    latest_quote_at = (
        sa_select(func.max(col(CourierQuote.created_at)))
        .where(col(CourierQuote.order_id) == col(Order.id))
        .scalar_subquery()
    )
    # GREATEST ignores NULLs in Postgres: the later of acceptance, rejection
    # and claim is when the accepted stage last moved.
    accepted_moved = (
        sa_select(
            func.greatest(
                col(OrderCourier.accepted_at), col(OrderCourier.payment_claim_rejected_at)
            )
        )
        .where(col(OrderCourier.order_id) == col(Order.id))
        .scalar_subquery()
    )
    claimed_at = (
        sa_select(col(Payment.customer_claimed_at))
        .where(col(Payment.order_id) == col(Order.id))
        .scalar_subquery()
    )
    eta_to = (
        sa_select(col(OrderCourier.eta_to))
        .where(col(OrderCourier.order_id) == col(Order.id))
        .scalar_subquery()
    )
    status = col(Order.status)
    return or_(
        and_(status == OrderStatus.Pending, col(Order.placed_at) < cutoff),
        and_(status == OrderStatus.Quoted, latest_quote_at < cutoff),
        and_(status == OrderStatus.Accepted, func.greatest(accepted_moved, claimed_at) < cutoff),
        and_(status == OrderStatus.Dispatched, eta_to < overdue_before),
    )
