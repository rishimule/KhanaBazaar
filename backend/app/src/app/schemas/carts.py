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
    items: List[CartItemRead]
    subtotal: float


class CartListResponse(BaseModel):
    carts: List[CartRead]


class CartItemAdd(BaseModel):
    store_id: int
    inventory_id: int
    quantity: int = Field(gt=0)


class CartItemUpdate(BaseModel):
    quantity: int = Field(gt=0)


class CartSyncItem(BaseModel):
    inventory_id: int
    quantity: int = Field(gt=0)


class CartSyncCart(BaseModel):
    store_id: int
    items: List[CartSyncItem]


class CartSyncRequest(BaseModel):
    carts: List[CartSyncCart]


class DroppedSyncItem(BaseModel):
    inventory_id: int
    reason: str


class CartSyncResponse(BaseModel):
    carts: List[CartRead]
    dropped: List[DroppedSyncItem]
