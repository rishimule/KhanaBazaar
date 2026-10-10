# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Order receipts (spec docs/superpowers/specs/2026-10-10-order-receipts-design.md).

The only writer of `order_receipt`. A receipt is issued once, inside the
transaction that marks the order delivered, from a frozen copy of everything
it prints, so a seller's later profile edit never changes an issued receipt.
Numbers run per store per Indian financial year (from 1 April, IST).
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, NamedTuple, Optional

from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.base import AccountStatus, User
from app.models.commerce import (
    Delivery,
    DeliveryMode,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from app.models.courier import OrderCourier
from app.models.profile import CustomerProfile, SellerProfile
from app.models.receipt import OrderReceipt
from app.models.returns import ReturnRequest, ReturnStatus
from app.models.store import Store
from app.schemas.receipts import (
    ReceiptAmounts,
    ReceiptCustomer,
    ReceiptDeliverTo,
    ReceiptItem,
    ReceiptLaterChanges,
    ReceiptOrderInfo,
    ReceiptPayment,
    ReceiptRead,
    ReceiptReturnNote,
    ReceiptSeller,
    ReceiptSettled,
    ReceiptSnapshotV1,
)
from app.utils.address import format_address
from app.utils.currency import format_inr
from app.utils.delivery_window import IST

logger = logging.getLogger(__name__)

SNAPSHOT_VERSION = 1
IssuedVia = Literal["delivery", "backfill"]

# English labels for the email; the web page uses Order.payment.method.*.
_METHOD_LABELS: dict[str, str] = {
    "upi": "UPI",
    "cash": "Cash on delivery",
    "credit": "Credit",
    "net_banking": "Bank transfer",
    "pay_at_store": "Paid at store",
}


def fiscal_year_for(moment: datetime) -> int:
    """Start year of the Indian financial year holding `moment`, judged by its
    IST calendar date: 31 Mar 20:00 UTC is already 1 Apr in IST."""
    local = moment.astimezone(IST)
    return local.year if local.month >= 4 else local.year - 1


def format_receipt_number(fiscal_year: int, seq: int) -> str:
    """`RC-2627-000045`: 14 chars, and a 7-digit seq makes 15, inside the
    16 GST allows an invoice number, so an invoice series can share the shape."""
    return f"RC-{fiscal_year % 100:02d}{(fiscal_year + 1) % 100:02d}-{seq:06d}"


@dataclass(frozen=True)
class ReceiptInputs:
    """Every row the snapshot reads, loaded by `load_inputs`."""

    order: Order
    items: list[OrderItem]
    payment: Optional[Payment]
    store: Store
    store_address: Optional[Address]
    seller: Optional[SellerProfile]
    customer: Optional[CustomerProfile]
    courier: Optional[OrderCourier]


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    return (value.strip() or None) if value else None


def _settled(payment: Optional[Payment]) -> ReceiptSettled:
    if payment is None:
        return "unpaid"
    if payment.method == PaymentMethod.Credit:
        return "on_credit"
    # Refunded still counts as paid: the sale was paid, and the refund shows
    # as a later change beside the receipt (a backfill can meet one).
    if payment.status in (PaymentStatus.Paid, PaymentStatus.Refunded):
        return "paid"
    return "unpaid"


def _customer_name(profile: Optional[CustomerProfile]) -> str:
    if profile is None:
        return "Customer"
    parts = (profile.first_name, profile.last_name)
    return " ".join(p.strip() for p in parts if p and p.strip()) or "Customer"


def _deliver_to(inputs: ReceiptInputs) -> Optional[ReceiptDeliverTo]:
    order = inputs.order
    address = order.delivery_address_snapshot or None
    if order.delivery_mode == DeliveryMode.Pickup:
        return None
    if order.delivery_mode == DeliveryMode.Courier and inputs.courier is not None:
        return ReceiptDeliverTo(
            name=inputs.courier.recipient_name,
            phone=inputs.courier.recipient_phone,
            address=address,
        )
    return ReceiptDeliverTo(address=address)


def build_snapshot(inputs: ReceiptInputs, *, delivered_at: datetime) -> ReceiptSnapshotV1:
    """Pure: everything the receipt prints, from rows already loaded."""
    order, payment, seller = inputs.order, inputs.payment, inputs.seller
    assert order.id is not None
    return ReceiptSnapshotV1(
        order=ReceiptOrderInfo(
            id=order.id,
            placed_at=order.placed_at,
            delivered_at=delivered_at,
            delivery_mode=order.delivery_mode.value,
            service_name=order.service_name_snapshot,
        ),
        seller=ReceiptSeller(
            business_name=seller.business_name if seller is not None else inputs.store.name,
            store_name=inputs.store.name,
            store_address=(
                format_address(inputs.store_address) if inputs.store_address is not None else None
            ),
            gstin=_blank_to_none(seller.gst_number) if seller is not None else None,
            fssai=_blank_to_none(seller.fssai_license) if seller is not None else None,
        ),
        customer=ReceiptCustomer(
            name=_customer_name(inputs.customer),
            phone=inputs.customer.phone if inputs.customer is not None else None,
        ),
        deliver_to=_deliver_to(inputs),
        items=[
            ReceiptItem(
                name=item.product_name_snapshot,
                quantity=item.quantity,
                unit_price=item.unit_price_snapshot,
                line_total=item.line_total,
            )
            for item in inputs.items
        ],
        amounts=ReceiptAmounts(
            subtotal=order.subtotal,
            delivery_fee=order.delivery_fee,
            delivery_fee_kind=(
                "courier" if order.delivery_mode == DeliveryMode.Courier else "delivery"
            ),
            total=order.total,
            store_credit_applied=order.store_credit_applied,
            amount_paid=payment.amount if payment is not None else 0.0,
        ),
        payment=ReceiptPayment(
            method=payment.method.value if payment is not None else None,
            settled=_settled(payment),
            paid_at=payment.paid_at if payment is not None else None,
        ),
    )


def payment_line(snapshot: ReceiptSnapshotV1) -> str:
    """The email's one-line "how it was paid". Same rule order as the web's
    lib/receipts.receiptPaymentKey; keep the two in step."""
    amounts, payment = snapshot.amounts, snapshot.payment
    if payment.settled == "unpaid":
        return "Payment not recorded"
    # Before the credit line: store credit can cover a postpaid order whole,
    # and "₹0.00 charged to the credit account" would be nonsense.
    if amounts.amount_paid == 0 and amounts.store_credit_applied > 0:
        return "Paid with store credit"
    if payment.settled == "on_credit":
        return (
            f"{format_inr(amounts.amount_paid)} charged to the credit account "
            f"with {snapshot.seller.store_name}"
        )
    method = _METHOD_LABELS.get(payment.method or "", "")
    return f"Paid {format_inr(amounts.amount_paid)} · {method}".rstrip(" ·")


_NEXT_SEQ_SQL = text(
    "INSERT INTO order_receipt_counter (store_id, fiscal_year, last_seq) "
    "VALUES (:store_id, :fiscal_year, 1) "
    "ON CONFLICT (store_id, fiscal_year) "
    "DO UPDATE SET last_seq = order_receipt_counter.last_seq + 1 "
    "RETURNING last_seq"
)


async def _next_seq(session: AsyncSession, store_id: int, fiscal_year: int) -> int:
    """Take the next number in the store's series. The upsert row-locks the
    counter until commit, so deliveries at one store queue here, and a
    rolled-back delivery gives its number back (no gaps)."""
    result = await session.execute(
        _NEXT_SEQ_SQL, {"store_id": store_id, "fiscal_year": fiscal_year}
    )
    return int(result.scalar_one())


async def load_inputs(session: AsyncSession, order: Order) -> ReceiptInputs:
    """Load every row the snapshot reads. The selects autoflush, so a payment
    marked paid earlier in the same transaction is read as paid."""
    assert order.id is not None
    items = (
        await session.exec(
            select(OrderItem)
            .where(OrderItem.order_id == order.id)
            .order_by(col(OrderItem.id))
        )
    ).all()
    payment = (await session.exec(select(Payment).where(Payment.order_id == order.id))).first()
    store = await session.get(Store, order.store_id)
    if store is None:
        raise LookupError(f"store {order.store_id} missing for order {order.id}")
    courier = None
    if order.delivery_mode == DeliveryMode.Courier:
        courier = (
            await session.exec(select(OrderCourier).where(OrderCourier.order_id == order.id))
        ).first()
    return ReceiptInputs(
        order=order,
        items=list(items),
        payment=payment,
        store=store,
        store_address=await session.get(Address, store.address_id),
        seller=await session.get(SellerProfile, store.seller_profile_id),
        customer=await session.get(CustomerProfile, order.customer_profile_id),
        courier=courier,
    )


async def issue_for_order(
    session: AsyncSession, order: Order, *, delivered_at: datetime, via: IssuedVia
) -> OrderReceipt:
    """Build, number and add the order's receipt. Flushes; the caller commits.
    The snapshot is built before the number is taken, so a builder error
    never touches the counter."""
    assert order.id is not None
    snapshot = build_snapshot(await load_inputs(session, order), delivered_at=delivered_at)
    fiscal_year = fiscal_year_for(delivered_at)
    seq = await _next_seq(session, order.store_id, fiscal_year)
    receipt = OrderReceipt(
        order_id=order.id,
        store_id=order.store_id,
        fiscal_year=fiscal_year,
        seq=seq,
        number=format_receipt_number(fiscal_year, seq),
        issued_at=delivered_at,
        issued_via=via,
        snapshot_version=SNAPSHOT_VERSION,
        snapshot=snapshot.model_dump(mode="json"),
    )
    session.add(receipt)
    await session.flush()
    return receipt


async def issue_in_savepoint(
    session: AsyncSession, order: Order, *, delivered_at: datetime
) -> None:
    """The live-path hook (spec §4): issue inside a SAVEPOINT and swallow any
    failure, so a receipt bug can never stop a seller completing a delivery.
    Rolling the savepoint back also returns the number; the hourly sweep
    issues the missing receipt later."""
    order_id = order.id
    # Flush the delivery's own changes first, outside the try: begin_nested()
    # would otherwise flush them inside it, and a failure there is the
    # delivery's, not the receipt's — it must surface, not be swallowed.
    await session.flush()
    try:
        async with session.begin_nested():
            await issue_for_order(session, order, delivered_at=delivered_at, via="delivery")
    except Exception:
        logger.exception("receipt_issue_failed order_id=%s", order_id)


class BackfillResult(NamedTuple):
    issued: int
    failed: int


async def issue_missing(
    session: AsyncSession, *, limit: Optional[int] = None
) -> BackfillResult:
    """Issue receipts for delivered orders that have none, oldest delivery
    first, committing each one on its own so a crash resumes where it
    stopped (spec §7). Used by the deploy backfill (no limit) and the hourly
    sweep. Never emails. A failing order is logged, counted and skipped; the
    next run retries it."""
    moment = func.coalesce(Delivery.delivered_at, Order.placed_at)
    stmt = (
        select(Order.id, moment)
        .outerjoin(Delivery, col(Delivery.order_id) == col(Order.id))
        .outerjoin(OrderReceipt, col(OrderReceipt.order_id) == col(Order.id))
        .where(Order.status == OrderStatus.Delivered, col(OrderReceipt.id).is_(None))
        .order_by(moment, col(Order.id))
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    pending = (await session.exec(stmt)).all()
    issued = failed = 0
    for order_id, delivered_at in pending:
        try:
            order = await session.get(Order, order_id)
            if order is None:
                continue
            await issue_for_order(session, order, delivered_at=delivered_at, via="backfill")
            await session.commit()
            issued += 1
        except IntegrityError:
            # An overlapping run (sweep vs deploy backfill) got there first.
            await session.rollback()
            logger.info("receipt_backfill_skipped order_id=%s already issued", order_id)
        except Exception:
            await session.rollback()
            failed += 1
            logger.exception("receipt_backfill_failed order_id=%s", order_id)
    return BackfillResult(issued=issued, failed=failed)


# Returns that never happened don't belong in the "after this receipt" note.
_HIDDEN_RETURN_STATUSES = (ReturnStatus.rejected, ReturnStatus.withdrawn, ReturnStatus.expired)


async def read_receipt(session: AsyncSession, order_id: int) -> Optional[ReceiptRead]:
    """The receipt plus its live `later_changes` (spec §5.3), or None when
    the order has no receipt yet. The receipt itself is never edited."""
    receipt = (
        await session.exec(select(OrderReceipt).where(OrderReceipt.order_id == order_id))
    ).first()
    if receipt is None:
        return None
    payment = (await session.exec(select(Payment).where(Payment.order_id == order_id))).first()
    returns = (
        await session.exec(
            select(ReturnRequest.id, ReturnRequest.status)
            .where(
                ReturnRequest.order_id == order_id,
                col(ReturnRequest.status).notin_(_HIDDEN_RETURN_STATUSES),
            )
            .order_by(col(ReturnRequest.id))
        )
    ).all()
    return ReceiptRead(
        number=receipt.number,
        issued_at=receipt.issued_at,
        issued_via=receipt.issued_via,
        created_at=receipt.created_at,
        order_id=receipt.order_id,
        snapshot=ReceiptSnapshotV1.model_validate(receipt.snapshot),
        later_changes=ReceiptLaterChanges(
            refunded_at=payment.refunded_at if payment is not None else None,
            returns=[
                ReceiptReturnNote(id=return_id, status=ReturnStatus(status).value)
                for return_id, status in returns
                if return_id is not None
            ],
        ),
    )


def _ist(moment: datetime, fmt: str) -> str:
    return moment.astimezone(IST).strftime(fmt)


def email_context(receipt: OrderReceipt) -> dict[str, object]:
    """Template variables for `order_receipt` (both recipients; the caller
    adds `recipient`). Every key is always present: the templates run under
    StrictUndefined."""
    snap = ReceiptSnapshotV1.model_validate(receipt.snapshot)
    is_pickup = snap.order.delivery_mode == DeliveryMode.Pickup.value
    return {
        "order_id": snap.order.id,
        "number": receipt.number,
        "issued_label": _ist(receipt.issued_at, "%d %b %Y, %I:%M %p"),
        "reissued_label": (
            _ist(receipt.created_at, "%d %b %Y") if receipt.issued_via == "backfill" else None
        ),
        "headline": "Collected" if is_pickup else "Delivered",
        "is_pickup": is_pickup,
        "service_name": snap.order.service_name,
        "store_name": snap.seller.store_name,
        "seller": snap.seller.model_dump(),
        "customer": snap.customer.model_dump(),
        "deliver_to": snap.deliver_to.model_dump() if snap.deliver_to is not None else None,
        "items": [item.model_dump() for item in snap.items],
        "amounts": snap.amounts.model_dump(),
        "payment_line": payment_line(snap),
    }


@dataclass(frozen=True)
class ReceiptMail:
    context: dict[str, object]
    customer_email: Optional[str]
    customer_active: bool
    seller_email: Optional[str]
    seller_active: bool


async def load_receipt_mail(session: AsyncSession, order_id: int) -> Optional[ReceiptMail]:
    """Everything the receipt email needs, or None when the order has no
    receipt (the worker then sends the plain "delivered" email instead)."""
    receipt = (
        await session.exec(select(OrderReceipt).where(OrderReceipt.order_id == order_id))
    ).first()
    order = await session.get(Order, order_id)
    if receipt is None or order is None:
        return None
    customer_user = (
        await session.exec(
            select(User)
            .join(CustomerProfile, col(CustomerProfile.user_id) == col(User.id))
            .where(CustomerProfile.id == order.customer_profile_id)
        )
    ).first()
    seller_user = (
        await session.exec(
            select(User)
            .join(SellerProfile, col(SellerProfile.user_id) == col(User.id))
            .join(Store, col(Store.seller_profile_id) == col(SellerProfile.id))
            .where(Store.id == order.store_id)
        )
    ).first()
    return ReceiptMail(
        context=email_context(receipt),
        customer_email=customer_user.email if customer_user is not None else None,
        customer_active=(
            customer_user is not None and customer_user.account_status == AccountStatus.active
        ),
        seller_email=seller_user.email if seller_user is not None else None,
        seller_active=seller_user is not None and seller_user.is_active,
    )
