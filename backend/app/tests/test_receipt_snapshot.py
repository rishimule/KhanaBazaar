# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Pure receipt helpers (spec 2026-10-10 §2.2, §3). No database."""
from datetime import datetime, timezone

import pytest

from app.models.address import Address
from app.models.commerce import (
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
from app.models.store import Store
from app.schemas.receipts import ReceiptSnapshotV1
from app.services.receipts import (
    ReceiptInputs,
    build_snapshot,
    fiscal_year_for,
    format_receipt_number,
    payment_line,
)

UTC = timezone.utc
PLACED = datetime(2026, 10, 10, 8, 0, tzinfo=UTC)
DELIVERED = datetime(2026, 10, 10, 9, 30, tzinfo=UTC)


def _inputs(
    *,
    mode: DeliveryMode = DeliveryMode.DoorDelivery,
    method: PaymentMethod = PaymentMethod.Upi,
    status: PaymentStatus = PaymentStatus.Paid,
    amount: float = 110.0,
    delivery_fee: float = 10.0,
    store_credit: float = 0.0,
    with_payment: bool = True,
    courier: OrderCourier | None = None,
    gst: str | None = "29ABCDE1234F1Z5",
) -> ReceiptInputs:
    order = Order(
        id=42,
        customer_profile_id=1,
        store_id=7,
        service_id=3,
        service_name_snapshot="Grocery",
        delivery_address_id=1,
        delivery_address_snapshot="12 MG Road, Bengaluru, Karnataka 560001, India",
        delivery_mode=mode,
        status=OrderStatus.Delivered,
        subtotal=100.0,
        delivery_fee=delivery_fee,
        tax=0.0,
        total=100.0 + delivery_fee,
        store_credit_applied=store_credit,
        placed_at=PLACED,
    )
    items = [
        OrderItem(
            order_id=42,
            product_name_snapshot="Apple",
            unit_price_snapshot=50.0,
            quantity=2,
            line_total=100.0,
        )
    ]
    payment = (
        Payment(
            order_id=42,
            amount=amount,
            method=method,
            status=status,
            paid_at=DELIVERED if status == PaymentStatus.Paid else None,
        )
        if with_payment
        else None
    )
    store = Store(id=7, name="Store A", seller_profile_id=5, address_id=9)
    store_address = Address(
        address_line1="1 Market St",
        city="Bengaluru",
        state="Karnataka",
        pincode="560002",
        country="India",
    )
    seller = SellerProfile(
        id=5,
        user_id=2,
        first_name="S",
        phone="+919800000010",
        business_name="S1 Traders",
        gst_number=gst,
        fssai_license=None,
        business_address_id=9,
    )
    customer = CustomerProfile(
        id=1, user_id=3, first_name="Asha", last_name="Rao", phone="+919800000001"
    )
    return ReceiptInputs(
        order=order,
        items=items,
        payment=payment,
        store=store,
        store_address=store_address,
        seller=seller,
        customer=customer,
        courier=courier,
    )


@pytest.mark.parametrize(
    "moment,expected",
    [
        (datetime(2026, 3, 31, 18, 29, tzinfo=UTC), 2025),  # 23:59 IST, 31 Mar
        (datetime(2026, 3, 31, 18, 30, tzinfo=UTC), 2026),  # 00:00 IST, 1 Apr
        (datetime(2027, 1, 15, 12, 0, tzinfo=UTC), 2026),
        (datetime(2026, 4, 1, 0, 0, tzinfo=UTC), 2026),
    ],
)
def test_fiscal_year_is_judged_in_ist(moment: datetime, expected: int) -> None:
    assert fiscal_year_for(moment) == expected


def test_receipt_number_format() -> None:
    assert format_receipt_number(2026, 45) == "RC-2627-000045"
    assert format_receipt_number(2099, 1) == "RC-9900-000001"
    wide = format_receipt_number(2026, 1_234_567)
    assert wide == "RC-2627-1234567" and len(wide) <= 16


def test_door_upi_snapshot() -> None:
    snap = build_snapshot(_inputs(), delivered_at=DELIVERED)
    assert snap.version == 1
    assert snap.order.id == 42 and snap.order.delivery_mode == "door_delivery"
    assert snap.order.delivered_at == DELIVERED and snap.order.placed_at == PLACED
    assert snap.order.service_name == "Grocery"
    assert snap.seller.business_name == "S1 Traders"
    assert snap.seller.store_name == "Store A"
    assert snap.seller.store_address == "1 Market St, Bengaluru, Karnataka 560002, India"
    assert snap.seller.gstin == "29ABCDE1234F1Z5" and snap.seller.fssai is None
    assert snap.customer.name == "Asha Rao" and snap.customer.phone == "+919800000001"
    assert snap.deliver_to is not None and snap.deliver_to.name is None
    assert snap.deliver_to.address == "12 MG Road, Bengaluru, Karnataka 560001, India"
    assert [i.model_dump() for i in snap.items] == [
        {"name": "Apple", "quantity": 2, "unit_price": 50.0, "line_total": 100.0}
    ]
    assert snap.amounts.model_dump() == {
        "subtotal": 100.0,
        "delivery_fee": 10.0,
        "delivery_fee_kind": "delivery",
        "total": 110.0,
        "store_credit_applied": 0.0,
        "amount_paid": 110.0,
    }
    assert snap.payment.method == "upi" and snap.payment.settled == "paid"
    assert snap.payment.paid_at == DELIVERED
    assert payment_line(snap) == "Paid ₹110.00 · UPI"


@pytest.mark.parametrize(
    "method,status,settled,line",
    [
        (PaymentMethod.Cash, PaymentStatus.Paid, "paid", "Paid ₹110.00 · Cash on delivery"),
        (PaymentMethod.PayAtStore, PaymentStatus.Paid, "paid", "Paid ₹110.00 · Paid at store"),
        (PaymentMethod.NetBanking, PaymentStatus.Paid, "paid", "Paid ₹110.00 · Bank transfer"),
        (
            PaymentMethod.Credit,
            PaymentStatus.Pending,
            "on_credit",
            "₹110.00 charged to the credit account with Store A",
        ),
        (PaymentMethod.Upi, PaymentStatus.Pending, "unpaid", "Payment not recorded"),
        # A backfill can meet an already-refunded sale: it was still paid.
        (PaymentMethod.Upi, PaymentStatus.Refunded, "paid", "Paid ₹110.00 · UPI"),
    ],
)
def test_payment_settlement(
    method: PaymentMethod, status: PaymentStatus, settled: str, line: str
) -> None:
    snap = build_snapshot(_inputs(method=method, status=status), delivered_at=DELIVERED)
    assert snap.payment.settled == settled
    assert payment_line(snap) == line


def test_store_credit_covering_everything() -> None:
    snap = build_snapshot(_inputs(amount=0.0, store_credit=110.0), delivered_at=DELIVERED)
    assert snap.amounts.store_credit_applied == 110.0 and snap.amounts.amount_paid == 0.0
    assert snap.payment.settled == "paid"
    assert payment_line(snap) == "Paid with store credit"


def test_store_credit_covering_a_credit_order() -> None:
    snap = build_snapshot(
        _inputs(
            method=PaymentMethod.Credit,
            status=PaymentStatus.Pending,
            amount=0.0,
            store_credit=110.0,
        ),
        delivered_at=DELIVERED,
    )
    assert snap.payment.settled == "on_credit"
    assert payment_line(snap) == "Paid with store credit"


def test_missing_payment_row_is_unpaid() -> None:
    snap = build_snapshot(_inputs(with_payment=False), delivered_at=DELIVERED)
    assert snap.payment.settled == "unpaid" and snap.payment.method is None
    assert snap.amounts.amount_paid == 0.0
    assert payment_line(snap) == "Payment not recorded"


def test_pickup_has_no_deliver_to() -> None:
    snap = build_snapshot(
        _inputs(mode=DeliveryMode.Pickup, delivery_fee=0.0, amount=100.0), delivered_at=DELIVERED
    )
    assert snap.deliver_to is None
    assert snap.order.delivery_mode == "pickup"


def test_courier_names_the_recipient_and_the_charge() -> None:
    courier = OrderCourier(order_id=42, recipient_name="Ravi Rao", recipient_phone="+919811111111")
    snap = build_snapshot(
        _inputs(mode=DeliveryMode.Courier, delivery_fee=120.0, amount=220.0, courier=courier),
        delivered_at=DELIVERED,
    )
    assert snap.amounts.delivery_fee_kind == "courier"
    assert snap.deliver_to is not None
    assert (snap.deliver_to.name, snap.deliver_to.phone) == ("Ravi Rao", "+919811111111")


def test_blank_gstin_is_dropped() -> None:
    snap = build_snapshot(_inputs(gst="   "), delivered_at=DELIVERED)
    assert snap.seller.gstin is None


def test_snapshot_survives_json_round_trip() -> None:
    snap = build_snapshot(_inputs(), delivered_at=DELIVERED)
    assert ReceiptSnapshotV1.model_validate(snap.model_dump(mode="json")) == snap
