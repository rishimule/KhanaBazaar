"""Wire schemas for inventory bulk endpoints."""

from typing import Literal

from pydantic import BaseModel, Field

BulkErrorCode = Literal[
    "PRICE_INVALID",
    "STOCK_INVALID",
    "PRODUCT_NOT_FOUND",
    "SERVICE_NOT_APPROVED",
    "DUPLICATE_PRODUCT",
    "ROW_LIMIT",
]


class BulkInventoryItem(BaseModel):
    """One row of a bulk upsert payload.

    No `inventory_id` field — the server resolves insert vs update by
    looking up `(store_id, product_id)`.
    """

    product_id: int
    price: float
    stock: int
    is_available: bool = True


class BulkInventoryRequest(BaseModel):
    items: list[BulkInventoryItem] = Field(default_factory=list)


class BulkInventoryError(BaseModel):
    index: int
    product_id: int
    code: BulkErrorCode
    message: str


class EligibleProduct(BaseModel):
    id: int
    name: str
    base_price: float
    subcategory_id: int
    subcategory_name: str
    category_id: int
    category_name: str
    service_id: int
    service_name: str
    in_inventory: bool
