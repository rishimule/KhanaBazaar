# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Pydantic schemas for the price-comparison endpoints.

See `docs/superpowers/specs/2026-05-14-checkout-price-comparison-design.md`
for the full contract.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# GET /api/v1/carts/{store_id}/{service_id}/compare
# ---------------------------------------------------------------------------


class ComparisonItem(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    inventory_id: Optional[int]
    unit_price: float
    is_available: bool
    stock: int
    line_total: float
    imputed: bool


class ComparisonAlternative(BaseModel):
    id: int
    name: str
    distance_km: float
    covered_count: int
    missing_count: int
    covered_subtotal: float
    imputed_subtotal: float
    effective_total: float
    items: List[ComparisonItem]


class CompareResponse(BaseModel):
    alternatives: List[ComparisonAlternative]


# ---------------------------------------------------------------------------
# POST /api/v1/carts/{store_id}/{service_id}/replace
# ---------------------------------------------------------------------------


class ReplaceItemRequest(BaseModel):
    inventory_id: int
    quantity: int = Field(gt=0)


class ReplaceRequest(BaseModel):
    # Upper bound matches the spec's MVP cart-size assumption and prevents
    # an unauthenticated-cost amplification path on this endpoint (each
    # item triggers two DB lookups). 200 is well past any realistic cart.
    items: List[ReplaceItemRequest] = Field(min_length=1, max_length=200)


ReplaceAdjustmentReason = Literal[
    "stock_capped",
    "stock_exhausted",
    "item_unavailable",
]


class ReplaceAdjustment(BaseModel):
    inventory_id: int
    requested_quantity: int
    granted_quantity: int
    reason: ReplaceAdjustmentReason


# `cart` is intentionally typed loose here; the route handler builds the
# response by reusing the existing CartRead-shaped dict serializer in
# api/carts.py so we don't duplicate that logic.
class ReplaceResponse(BaseModel):
    cart: dict[str, object]
    adjustments: List[ReplaceAdjustment]
