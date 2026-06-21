# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.models.commerce import (
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
    subtotal: float
    delivery_fee: float
    tax: float
    total: float
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


class OrderListResponse(BaseModel):
    orders: List[OrderRead]
    total: int = 0
    page: int = 1
    page_size: int = 50


class PlaceOrderRequest(BaseModel):
    customer_address_id: int = Field(gt=0)
    store_id: int = Field(gt=0)
    service_id: int = Field(gt=0)
    payment_method: PaymentMethod
    preferred_delivery_date: Optional[date] = None
    preferred_delivery_window: Optional[str] = None

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
