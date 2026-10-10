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
from typing import Literal, Optional

from app.models.address import Address
from app.models.commerce import (
    DeliveryMode,
    Order,
    OrderItem,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from app.models.courier import OrderCourier
from app.models.profile import CustomerProfile, SellerProfile
from app.models.store import Store
from app.schemas.receipts import (
    ReceiptAmounts,
    ReceiptCustomer,
    ReceiptDeliverTo,
    ReceiptItem,
    ReceiptOrderInfo,
    ReceiptPayment,
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
    if payment.settled == "on_credit":
        return (
            f"{format_inr(amounts.amount_paid)} charged to the credit account "
            f"with {snapshot.seller.store_name}"
        )
    if payment.settled == "unpaid":
        return "Payment not recorded"
    if amounts.amount_paid == 0 and amounts.store_credit_applied > 0:
        return "Paid with store credit"
    method = _METHOD_LABELS.get(payment.method or "", "")
    return f"Paid {format_inr(amounts.amount_paid)} · {method}".rstrip(" ·")
