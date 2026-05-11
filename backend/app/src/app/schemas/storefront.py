# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Response schemas for the public storefront endpoint.

Tree-shaped payload built server-side so the store-detail page can render
in one round trip instead of joining `/catalog/products` against a
1500-row catalog client-side.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.schemas.stores import StoreRead


class StorefrontItem(BaseModel):
    inventory_id: int
    product_id: int
    product_slug: str
    product_name: str
    image_url: str | None
    description: str | None
    price: float
    stock: int


class StorefrontSubcategory(BaseModel):
    id: int
    slug: str
    name: str
    sort_order: int
    items: list[StorefrontItem]


class StorefrontCategory(BaseModel):
    id: int
    slug: str
    name: str
    sort_order: int
    subcategories: list[StorefrontSubcategory]


class StorefrontService(BaseModel):
    id: int
    slug: str
    name: str
    sort_order: int
    categories: list[StorefrontCategory]


class StorefrontResponse(BaseModel):
    store: StoreRead
    services: list[StorefrontService]
