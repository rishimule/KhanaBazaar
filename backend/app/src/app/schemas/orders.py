# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.models.commerce import (
    DeliveryMode,
    DeliveryStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
)
from app.utils.delivery_window import ist_today, validate_preferred_window


class OrderItemRead(BaseModel):
    id: int
    inventory_id: Optional[int]
    product_name_snapshot: str
    unit_price_snapshot: float
    quantity: int
    line_total: float


class PaymentRead(BaseModel):
    method: PaymentMethod
    status: PaymentStatus
    amount: float
    paid_at: Optional[datetime]
    # The customer's one-tap "I've paid" assertion. Never implies `status`.
    customer_claimed_at: Optional[datetime] = None
    # Courier refunds (spec §10.3): when the refund was recorded, and its UTR.
    refunded_at: Optional[datetime] = None
    refund_reference: Optional[str] = None


class DeliveryRead(BaseModel):
    status: DeliveryStatus
    packed_at: Optional[datetime]
    dispatched_at: Optional[datetime]
    delivered_at: Optional[datetime]
    otp: Optional[str] = None
    otp_locked: bool = False
    otp_attempts_remaining: int = 0


class OrderReviewInOrder(BaseModel):
    rating: int
    comment: Optional[str] = None


class CourierQuoteRead(BaseModel):
    id: int
    version: int
    courier_fee: float
    eta_min_days: int
    eta_max_days: int
    carrier_name: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime


class BankTransferRead(BaseModel):
    """The seller's bank details — only on an accepted courier order, only to
    its customer (spec D6)."""

    account_name: str
    account_number: str
    ifsc: str


class CourierRead(BaseModel):
    recipient_name: str
    recipient_phone: str
    # Seller/admin: every version, newest first. Customer: the latest only.
    quotes: List[CourierQuoteRead] = []
    revised: bool = False
    accepted_quote_id: Optional[int] = None
    accepted_at: Optional[datetime] = None
    eta_from: Optional[date] = None
    eta_to: Optional[date] = None
    payment_claim_rejected_at: Optional[datetime] = None
    payment_claim_rejected_note: Optional[str] = None
    carrier_name: Optional[str] = None
    tracking_number: Optional[str] = None
    tracking_url: Optional[str] = None
    tracking_updated_at: Optional[datetime] = None
    delivered_by: Optional[str] = None
    cancel_reason: Optional[str] = None
    cancelled_by: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    payment_reported_missing_at: Optional[datetime] = None
    refund_due: bool = False
    # Prepaid methods the seller can be paid by right now (pay-panel tabs).
    payable_methods: List[PaymentMethod] = []
    bank_transfer: Optional[BankTransferRead] = None


class CourierQuoteRequest(BaseModel):
    courier_fee: float = Field(ge=0, le=100000)
    eta_min_days: int = Field(ge=1, le=60)
    eta_max_days: int = Field(ge=1, le=60)
    carrier_name: Optional[str] = Field(default=None, max_length=80)
    note: Optional[str] = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _window(self) -> "CourierQuoteRequest":
        if self.eta_min_days > self.eta_max_days:
            raise ValueError("eta_min_days must be <= eta_max_days")
        return self


class CourierAcceptRequest(BaseModel):
    # Names the version the customer saw, so a revision mid-tap is caught.
    quote_id: int = Field(gt=0)


class PaymentClaimRequest(BaseModel):
    # Courier orders must say how they paid (spec D7); local UPI claims send
    # no body at all, as before.
    method: Optional[PaymentMethod] = None


class PaymentNotReceivedRequest(BaseModel):
    note: Optional[str] = Field(default=None, max_length=300)


class OrderRead(BaseModel):
    id: int
    store_id: int
    store_name: str
    service_id: int
    service_name: str
    delivery_eta_min_minutes: int = 30
    delivery_eta_max_minutes: int = 60
    preferred_delivery_date: Optional[date] = None
    preferred_delivery_window: Optional[str] = None
    customer_name: Optional[str] = None
    status: OrderStatus
    delivery_mode: DeliveryMode = DeliveryMode.DoorDelivery
    subtotal: float
    delivery_fee: float
    tax: float
    total: float
    # Gross `total` minus this is what the customer actually pays.
    store_credit_applied: float = 0.0
    placed_at: datetime
    delivery_address_snapshot: str
    store_latitude: Optional[float] = None
    store_longitude: Optional[float] = None
    delivery_latitude: Optional[float] = None
    delivery_longitude: Optional[float] = None
    items: List[OrderItemRead]
    payment: PaymentRead
    delivery: DeliveryRead
    review: Optional[OrderReviewInOrder] = None
    # Courier orders only (spec §13); None for door delivery and pickup.
    courier: Optional[CourierRead] = None


class OrderListResponse(BaseModel):
    orders: List[OrderRead]
    total: int = 0
    page: int = 1
    page_size: int = 50


class PlaceOrderRequest(BaseModel):
    customer_address_id: Optional[int] = Field(default=None, gt=0)
    store_id: int = Field(gt=0)
    service_id: int = Field(gt=0)
    payment_method: PaymentMethod
    delivery_mode: DeliveryMode = DeliveryMode.DoorDelivery
    preferred_delivery_date: Optional[date] = None
    preferred_delivery_window: Optional[str] = None
    # Store credit auto-applies; the checkout page offers an opt-out.
    apply_store_credit: bool = True
    # Courier only (spec §8.3): who the courier hands the parcel to. Validated
    # and normalized in services/checkout.py so the error codes stay strings.
    recipient_name: Optional[str] = Field(default=None, max_length=200)
    recipient_phone: Optional[str] = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def _check_preferred_window(self) -> "PlaceOrderRequest":
        validate_preferred_window(
            self.preferred_delivery_date,
            self.preferred_delivery_window,
            today=ist_today(),
        )
        return self


class TransitionRequest(BaseModel):
    to: Literal["packed", "dispatched", "delivered"]
    otp: Optional[str] = None
    reason: Optional[str] = None
    # Courier "Shipped" only; validated in services/orders.py so the error
    # carries a code. Generous max_length so our validator, not Pydantic, speaks.
    carrier_name: Optional[str] = Field(default=None, max_length=200)
    tracking_number: Optional[str] = Field(default=None, max_length=200)
    tracking_url: Optional[str] = Field(default=None, max_length=2000)


class CourierTrackingRequest(BaseModel):
    """Per field: omitted = leave alone, "" = clear."""

    carrier_name: Optional[str] = Field(default=None, max_length=200)
    tracking_number: Optional[str] = Field(default=None, max_length=200)
    tracking_url: Optional[str] = Field(default=None, max_length=2000)


class SellerOrderAlertSummary(BaseModel):
    """Cheap poll payload driving the seller Orders nav badge + new-order chime."""

    pending_count: int
    latest_pending_order_id: Optional[int] = None
    latest_pending_at: Optional[datetime] = None
