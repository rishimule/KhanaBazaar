# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SuggestTerm(BaseModel):
    text: str
    kind: Literal["product_name", "category", "subcategory"]


class SuggestStoreOfferBest(BaseModel):
    id: int
    name: str
    price: float
    is_available: bool


class SuggestProduct(BaseModel):
    id: int
    name: str
    image_url: Optional[str] = None
    min_price: float
    store_count: int
    best_store: Optional[SuggestStoreOfferBest] = None


class SuggestStore(BaseModel):
    id: int
    name: str
    service_ids: list[int]
    distance_km: Optional[float] = None


class SuggestResponse(BaseModel):
    query_id: UUID
    terms: list[SuggestTerm]
    products: list[SuggestProduct]
    stores: list[SuggestStore]


class PerStoreOffer(BaseModel):
    store_id: int
    store_name: str
    inventory_id: Optional[int] = None
    price: float
    stock: int
    is_available: bool
    is_serviceable: bool
    distance_km: Optional[float] = None


class ProductCard(BaseModel):
    id: int
    slug: str
    name: str
    image_url: Optional[str] = None
    brand: Optional[str] = None
    unit: Optional[str] = None
    service_id: int
    service_name: Optional[str] = None
    category_id: int
    subcategory_id: int
    min_price: float
    max_price: float
    in_stock_anywhere: bool
    per_store_offers: list[PerStoreOffer]


class FacetBuckets(BaseModel):
    service_id: dict[str, int] = Field(default_factory=dict)
    category_id: dict[str, int] = Field(default_factory=dict)
    min_price_bucket: dict[str, int] = Field(default_factory=dict)


class ProductsResponse(BaseModel):
    query_id: UUID
    query: str
    total: int
    page: int
    page_size: int
    products: list[ProductCard]
    facets: FacetBuckets
    applied_filters: dict[str, int | float | str]
    sort: str


class CompareStore(BaseModel):
    id: int
    name: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    distance_km: Optional[float] = None
    delivery_radius_km: float


class CompareOffer(BaseModel):
    store: CompareStore
    inventory_id: int
    price: float
    stock: int
    is_available: bool
    is_serviceable: bool


class CompareResponse(BaseModel):
    product: ProductCard
    offers: list[CompareOffer]


class ClickPayload(BaseModel):
    query_id: UUID
    clicked_product_id: Optional[int] = None
    clicked_store_id: Optional[int] = None
    position: int


class StoreSearchResponse(BaseModel):
    total: int
    page: int
    page_size: int
    stores: list[SuggestStore]


class BrowseProductCard(BaseModel):
    id: int
    slug: str
    name: str
    image_url: Optional[str] = None
    brand: Optional[str] = None
    unit: Optional[str] = None
    min_price: float
    max_price: float
    in_stock_anywhere: bool
    category_id: int


class BrowseCategory(BaseModel):
    id: int
    slug: str
    name: str
    products: list[BrowseProductCard]


class BrowseResponse(BaseModel):
    service_id: int
    service_name: str
    categories: list[BrowseCategory]
