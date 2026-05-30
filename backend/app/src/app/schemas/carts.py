# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import List

from pydantic import BaseModel, Field


class CartItemRead(BaseModel):
    id: int
    inventory_id: int
    product_id: int
    product_name: str
    unit_price: float
    quantity: int
    line_total: float


class CartRead(BaseModel):
    store_id: int
    store_name: str
    service_id: int
    service_name: str
    items: List[CartItemRead]
    subtotal: float
    min_order_value: float = 0.0
    delivery_eta_min_minutes: int = 30
    delivery_eta_max_minutes: int = 60


class CartListResponse(BaseModel):
    carts: List[CartRead]


class CartItemAdd(BaseModel):
    store_id: int
    service_id: int = Field(gt=0)
    inventory_id: int
    quantity: int = Field(gt=0)


class CartItemUpdate(BaseModel):
    quantity: int = Field(gt=0)


class CartSyncItem(BaseModel):
    inventory_id: int
    quantity: int = Field(gt=0)


class CartSyncCart(BaseModel):
    store_id: int
    service_id: int = Field(gt=0)
    items: List[CartSyncItem]


class CartSyncRequest(BaseModel):
    carts: List[CartSyncCart]


class DroppedSyncItem(BaseModel):
    inventory_id: int
    reason: str


class CartSyncResponse(BaseModel):
    carts: List[CartRead]
    dropped: List[DroppedSyncItem]
