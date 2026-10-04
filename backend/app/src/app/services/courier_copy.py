# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Copy for courier messages, plus the variables they need (spec §11.1).

Plain data in, plain strings out: the same `CourierVars` feeds the in-app row
(request path) and the email/WhatsApp tasks (worker path), so the channels can
never drift apart. English-only, like every message in the repo.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import AccountStatus, User
from app.models.commerce import Order, Payment
from app.models.courier import CourierQuote, OrderCourier
from app.models.profile import CustomerProfile, SellerProfile
from app.models.store import Store


@dataclass(frozen=True)
class Channels:
    email: bool = True
    whatsapp: bool = False


# In-app always (plus push for customers); these flags add email/WhatsApp.
CUSTOMER_EVENTS: dict[str, Channels] = {
    "quote_ready": Channels(whatsapp=True),
    "quote_revised": Channels(),
    "payment_not_received": Channels(),
    "payment_confirmed": Channels(),
    "auto_paid": Channels(),
    "tracking_updated": Channels(email=False),
    "refund_sent": Channels(),
    "reminder_quote": Channels(),
    "reminder_payment": Channels(),
    "reminder_arrival": Channels(),
}
SELLER_EVENTS: dict[str, Channels] = {
    "accepted": Channels(),
    "accepted_paid": Channels(),
    "payment_claimed": Channels(),
    # The generic cancellation email already reaches the seller.
    "customer_cancelled": Channels(email=False),
    "customer_received": Channels(),
    "payee_missing": Channels(),
    "reminder_quote": Channels(),
    "reminder_payment_check": Channels(),
    "reminder_overdue": Channels(),
    "reminder_refund": Channels(),
}


@dataclass(frozen=True)
class CourierVars:
    order_id: int
    status: str
    store_name: str
    customer_profile_id: int
    customer_active: bool
    customer_email: str | None
    customer_phone: str | None
    customer_phone_verified: bool
    seller_profile_id: int | None
    seller_active: bool
    seller_email: str | None
    total: float
    payable: float
    payment_method: str
    payment_status: str
    fee: float | None
    min_days: int | None
    max_days: int | None
    eta_from: date | None
    eta_to: date | None
    carrier_name: str | None
    tracking_number: str | None
    claim_note: str | None
    cancel_reason: str | None
    refund_reference: str | None


@dataclass(frozen=True)
class CourierMessage:
    title: str
    body: str


async def load_courier_vars(session: AsyncSession, order_id: int) -> CourierVars | None:
    """Everything a courier message needs, in one read. None when the order or
    its courier row is missing (callers then send nothing)."""
    order = (
        await session.exec(
            select(Order).where(Order.id == order_id).execution_options(populate_existing=True)
        )
    ).first()
    if order is None:
        return None
    row = (await session.exec(select(OrderCourier).where(OrderCourier.order_id == order_id))).first()
    if row is None:
        return None
    quote = (
        await session.exec(
            select(CourierQuote)
            .where(CourierQuote.order_id == order_id)
            .order_by(col(CourierQuote.version).desc())
        )
    ).first()
    payment = (await session.exec(select(Payment).where(Payment.order_id == order_id))).first()
    store = await session.get(Store, order.store_id)
    seller = await session.get(SellerProfile, store.seller_profile_id) if store else None
    seller_user = await session.get(User, seller.user_id) if seller else None
    customer = await session.get(CustomerProfile, order.customer_profile_id)
    customer_user = await session.get(User, customer.user_id) if customer else None
    return CourierVars(
        order_id=order_id,
        status=order.status.value,
        store_name=store.name if store else "the store",
        customer_profile_id=order.customer_profile_id,
        customer_active=bool(customer_user and customer_user.account_status == AccountStatus.active),
        customer_email=customer_user.email if customer_user else None,
        customer_phone=customer.phone if customer else None,
        customer_phone_verified=bool(customer and customer.phone_verified_at),
        seller_profile_id=seller.id if seller else None,
        seller_active=bool(seller_user and seller_user.account_status == AccountStatus.active),
        seller_email=seller_user.email if seller_user else None,
        total=order.total,
        payable=payment.amount if payment else order.total,
        payment_method=payment.method.value if payment else "upi",
        payment_status=payment.status.value if payment else "pending",
        fee=quote.courier_fee if quote else None,
        min_days=quote.eta_min_days if quote else None,
        max_days=quote.eta_max_days if quote else None,
        eta_from=row.eta_from,
        eta_to=row.eta_to,
        carrier_name=row.carrier_name,
        tracking_number=row.tracking_number,
        claim_note=row.payment_claim_rejected_note,
        cancel_reason=row.cancel_reason,
        refund_reference=payment.refund_reference if payment else None,
    )


def _money(amount: float | None) -> str:
    return f"₹{(amount or 0.0):.2f}"


def _day(d: date | None) -> str:
    return f"{d.day} {d:%b}" if d else "soon"


def _window(v: CourierVars) -> str:
    return f"{_day(v.eta_from)}–{_day(v.eta_to)}"


def _transit(v: CourierVars) -> str:
    if v.min_days is None or v.max_days is None:
        return "a few days"
    return f"{v.min_days}–{v.max_days} days"


def _method(method: str) -> str:
    return "UPI" if method == "upi" else "bank transfer"


def render_customer(event: str, v: CourierVars) -> CourierMessage:
    oid = v.order_id
    if event == "quote_ready":
        return CourierMessage(
            f"Courier quote for order #{oid}",
            f"{v.store_name}: {_money(v.fee)} courier charge, arriving {_transit(v)} "
            "after payment. Review it to accept and pay.",
        )
    if event == "quote_revised":
        return CourierMessage(
            f"Updated courier quote for order #{oid}",
            f"{v.store_name} changed the quote: {_money(v.fee)} courier charge, "
            f"arriving {_transit(v)} after payment.",
        )
    if event == "payment_not_received":
        note = f" Note from the store: {v.claim_note}" if v.claim_note else ""
        return CourierMessage(
            f"{v.store_name} hasn't received your payment",
            f"Order #{oid}: please check your payment of {_money(v.payable)} and try again.{note}",
        )
    if event == "payment_confirmed":
        return CourierMessage(
            f"Payment received for order #{oid}",
            f"{v.store_name} is preparing your order. Estimated arrival {_window(v)}.",
        )
    if event == "auto_paid":
        return CourierMessage(
            f"Order #{oid} confirmed",
            f"Nothing to pay — your store credit covers it. Estimated arrival {_window(v)}.",
        )
    if event == "tracking_updated":
        parts = [p for p in (v.carrier_name, v.tracking_number) if p]
        return CourierMessage(
            f"Tracking updated for order #{oid}",
            " · ".join(parts) if parts else "Open the order for tracking details.",
        )
    if event == "refund_sent":
        ref = f" (ref {v.refund_reference})" if v.refund_reference else ""
        return CourierMessage(
            f"Refund sent for order #{oid}",
            f"{v.store_name} says they refunded {_money(v.payable)}{ref}.",
        )
    if event == "reminder_quote":
        return CourierMessage(
            "Your courier quote is waiting",
            f"Order #{oid} from {v.store_name}: review the {_money(v.fee)} courier "
            "quote to accept and pay.",
        )
    if event == "reminder_payment":
        return CourierMessage(
            f"Complete your payment for order #{oid}",
            f"Pay {_money(v.payable)} to {v.store_name}, then tap I've paid.",
        )
    if event == "reminder_arrival":
        return CourierMessage(
            f"Has order #{oid} arrived?",
            f"If your parcel from {v.store_name} has arrived, tap I've received it.",
        )
    raise KeyError(event)


def render_seller(event: str, v: CourierVars) -> CourierMessage:
    oid = v.order_id
    if event == "accepted":
        return CourierMessage(
            f"Quote accepted for order #{oid}",
            f"The customer accepted {_money(v.payable)}. Wait for their payment before you ship.",
        )
    if event == "accepted_paid":
        return CourierMessage(
            f"Order #{oid} is ready to pack",
            "The customer accepted, and store credit covers the whole amount — nothing to collect.",
        )
    if event == "payment_claimed":
        return CourierMessage(
            f"Check the payment for order #{oid}",
            f"The customer says they paid {_money(v.payable)} by {_method(v.payment_method)}. "
            "Confirm once it reaches you.",
        )
    if event == "customer_cancelled":
        return CourierMessage(
            f"Order #{oid} cancelled by the customer",
            f"Reason: {v.cancel_reason}" if v.cancel_reason else "No reason given.",
        )
    if event == "customer_received":
        return CourierMessage(f"Order #{oid} delivered", "The customer confirmed they received it.")
    if event == "payee_missing":
        return CourierMessage(
            f"A customer can't pay for order #{oid}",
            "Add a UPI ID or turn on bank transfer so they can pay.",
        )
    if event == "reminder_quote":
        return CourierMessage(
            f"Send a courier quote for order #{oid}",
            "The customer is waiting for the courier charge and delivery time.",
        )
    if event == "reminder_payment_check":
        return CourierMessage(
            f"Confirm the payment for order #{oid}",
            f"The customer said they paid {_money(v.payable)}. Check your bank or UPI app.",
        )
    if event == "reminder_overdue":
        return CourierMessage(
            f"Order #{oid} is past its delivery date",
            "Check with the courier, then update the tracking or mark it delivered.",
        )
    if event == "reminder_refund":
        return CourierMessage(
            f"Refund still owed for order #{oid}",
            f"You owe the customer {_money(v.payable)}. Refund it, then tap Refund sent.",
        )
    raise KeyError(event)


def render_status(status: str, v: CourierVars) -> CourierMessage | None:
    """Courier copy for the generic status changes that keep flowing through
    api.orders.record_and_dispatch_notification. None = use the generic copy."""
    oid = v.order_id
    if status == "pending":
        return CourierMessage(
            f"Order #{oid} sent — awaiting courier quote",
            f"{v.store_name} will send you the courier charge and delivery time. Nothing to pay yet.",
        )
    if status == "packed":
        return CourierMessage(f"Order #{oid} packed", f"{v.store_name} has packed your order for the courier.")
    if status == "dispatched":
        parts = [p for p in (v.carrier_name, v.tracking_number) if p]
        via = f" via {' · '.join(parts)}" if parts else ""
        return CourierMessage(
            f"Order #{oid} shipped",
            f"Your parcel is on its way{via}. Estimated arrival {_window(v)}.",
        )
    if status == "delivered":
        return CourierMessage(f"Order #{oid} delivered", "Your courier order has been delivered. Enjoy!")
    if status == "cancelled":
        # Same rule as courier_rules.refund_owed: ₹0 (all store credit) owes nothing.
        if v.payment_status == "paid" and v.payable > 0:
            return CourierMessage(
                f"Order #{oid} cancelled",
                f"{v.store_name} owes you a refund of {_money(v.payable)}. "
                "We'll let you know when they send it.",
            )
        reason = f" Reason: {v.cancel_reason}" if v.cancel_reason else ""
        return CourierMessage(f"Order #{oid} cancelled", f"Your courier order was cancelled.{reason}")
    return None
