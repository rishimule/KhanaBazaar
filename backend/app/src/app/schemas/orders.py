# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.models.commerce import (
    DeliveryStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
)


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


class OrderRead(BaseModel):
    id: int
    store_id: int
    store_name: str
    customer_name: Optional[str] = None
    status: OrderStatus
    subtotal: float
    delivery_fee: float
    tax: float
    total: float
    placed_at: datetime
    delivery_address_snapshot: str
    items: List[OrderItemRead]
    payment: PaymentRead
    delivery: DeliveryRead


class OrderListResponse(BaseModel):
    orders: List[OrderRead]


class PlaceOrderRequest(BaseModel):
    customer_address_id: int = Field(gt=0)
    store_id: int = Field(gt=0)
    payment_method: PaymentMethod


class TransitionRequest(BaseModel):
    to: Literal["packed", "dispatched", "delivered"]
