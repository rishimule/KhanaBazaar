# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Pydantic schemas for admin-supervisor endpoints (``/api/v1/admin/*``)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.address import AddressPayload
from app.schemas.services import ServicePayload


class RewindOrderRequest(BaseModel):
    to_status: Literal["pending", "packed"]
    reason: str = Field(min_length=10, max_length=500)


class RefundOrderRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=500)


class OverrideDeliveryAddressRequest(BaseModel):
    address: AddressPayload
    reason: str = Field(min_length=10, max_length=500)


class AdminActionLogOut(BaseModel):
    id: str
    admin_user_id: int
    admin_email: str
    target_seller_id: int
    target_type: str
    target_id: int
    action: str
    before_json: Optional[dict[str, Any]] = None
    after_json: Optional[dict[str, Any]] = None
    reason: Optional[str] = None
    created_at: str


class ActivityLogPage(BaseModel):
    items: list[AdminActionLogOut]
    next_cursor: Optional[str] = None


class SellerHubSummary(BaseModel):
    seller_id: int
    business_name: str
    verification_status: str
    email: str
    store_id: Optional[int] = None
    active_order_count: int
    total_product_count: int
    services: list[ServicePayload] = []


class OrderServiceStat(BaseModel):
    service_id: int
    service_name: str
    count: int


class AdminMetricsRead(BaseModel):
    active_orders: int
    orders_today: int
    orders_this_month: int
    gmv_this_month: float
    gmv_last_month: float
    gmv_trend_pct: float
    active_master_products: int
    active_categories: int
    active_stores: int
    pending_applications: int
    approved_sellers: int
    rejected_sellers: int
    open_change_requests: int
    orders_by_service: list[OrderServiceStat]


class AdminInventoryRow(BaseModel):
    """Inventory row enriched with the master product name for admin UI display."""

    id: int
    store_id: int
    product_id: int
    product_name: str
    product_brand: Optional[str] = None
    product_unit: Optional[str] = None
    price: float
    stock: int
    is_available: bool
