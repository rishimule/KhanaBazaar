# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Wire-format model for services. Mirrors the shape returned by
GET /catalog/services so frontend code can reuse a single Service type."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ServicePayload(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    slug: str
    name: str
    description: Optional[str] = None
    is_active: bool
    sort_order: int
    free_delivery_threshold: Optional[float] = None
    delivery_fee: Optional[float] = None
    delivery_eta_min_minutes: int = 30
    delivery_eta_max_minutes: int = 60
    pickup_enabled: bool = False
    is_paused: bool = False
    pause_reason: Optional[str] = None
    paused_until: Optional[str] = None
