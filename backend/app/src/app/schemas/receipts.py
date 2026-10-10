# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Order receipt shapes (spec 2026-10-10-order-receipts-design.md §3, §5.1).

`ReceiptSnapshotV1` is what `order_receipt.snapshot` stores: everything the
receipt prints, frozen at issue time. `ReceiptRead` is the API read model;
its `later_changes` is computed live and is never part of the receipt.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class ReceiptOrderInfo(BaseModel):
    id: int
    placed_at: datetime
    delivered_at: datetime
    # DeliveryMode value: "door_delivery" | "pickup" | "courier".
    delivery_mode: str
    service_name: str


class ReceiptSeller(BaseModel):
    business_name: str
    store_name: str
    store_address: Optional[str] = None
    gstin: Optional[str] = None
    fssai: Optional[str] = None


class ReceiptCustomer(BaseModel):
    name: str
    phone: Optional[str] = None


class ReceiptDeliverTo(BaseModel):
    # Courier orders name a recipient; door orders go to the account holder.
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class ReceiptItem(BaseModel):
    name: str
    quantity: int
    unit_price: float
    line_total: float


class ReceiptAmounts(BaseModel):
    subtotal: float
    delivery_fee: float
    delivery_fee_kind: Literal["delivery", "courier"]
    total: float
    store_credit_applied: float
    # payment.amount: what the customer paid (or owes on credit) after store credit.
    amount_paid: float


ReceiptSettled = Literal["paid", "on_credit", "unpaid"]


class ReceiptPayment(BaseModel):
    # PaymentMethod value, or None when the order has no payment row.
    method: Optional[str] = None
    settled: ReceiptSettled
    paid_at: Optional[datetime] = None


class ReceiptSnapshotV1(BaseModel):
    version: Literal[1] = 1
    order: ReceiptOrderInfo
    seller: ReceiptSeller
    customer: ReceiptCustomer
    deliver_to: Optional[ReceiptDeliverTo] = None  # None for pickup
    items: list[ReceiptItem]
    amounts: ReceiptAmounts
    payment: ReceiptPayment


class ReceiptReturnNote(BaseModel):
    id: int
    status: str


class ReceiptLaterChanges(BaseModel):
    refunded_at: Optional[datetime] = None
    returns: list[ReceiptReturnNote] = []


class ReceiptRead(BaseModel):
    number: str
    issued_at: datetime
    # "delivery" | "backfill"
    issued_via: str
    created_at: datetime
    order_id: int
    snapshot: ReceiptSnapshotV1
    later_changes: ReceiptLaterChanges
