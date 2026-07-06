# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Wire-format response for GET /api/v1/stores/{store_id}/products/{product_id}.

Per-store product detail. Powers both the in-app intercepted modal and the
shareable full page. Translation joins resolve breadcrumb names with English
fallback, matching the storefront response.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class StoreSummary(BaseModel):
    id: int
    name: str
    is_premium: bool = False


class ServiceLite(BaseModel):
    id: int
    name: str


class ProductImagePayload(BaseModel):
    url: str
    position: int


class MasterProductPayload(BaseModel):
    id: int
    name: str
    description: str
    image_url: Optional[str] = None
    images: list[ProductImagePayload] = []
    category_id: int
    subcategory_id: int
    subcategory_name: str
    base_price: float


class InventoryWithProductPayload(BaseModel):
    id: int
    store_id: int
    product_id: int
    price: float
    stock: int
    is_available: bool
    product: MasterProductPayload


class BreadcrumbPayload(BaseModel):
    service_id: int
    service_name: str
    category_id: int
    category_name: str
    subcategory_id: int
    subcategory_name: str


class StoreProductDetailResponse(BaseModel):
    store: StoreSummary
    service: ServiceLite
    inventory: InventoryWithProductPayload
    breadcrumb: BreadcrumbPayload
