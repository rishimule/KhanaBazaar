# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Wire-format models for store endpoints."""

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.address import AddressPayload
from app.schemas.services import ServicePayload


class StoreCreate(BaseModel):
    name: str
    address: AddressPayload
    delivery_radius_km: float = Field(default=5.0, ge=0.5, le=50.0)
    pin_confirmed: bool = False


class StoreUpdate(BaseModel):
    name: Optional[str] = None
    delivery_radius_km: Optional[float] = Field(default=None, ge=0.5, le=50.0)
    pin_confirmed: Optional[bool] = None


class StoreRead(BaseModel):
    id: int
    name: str
    address: AddressPayload
    is_active: bool
    seller_id: int
    services: list[ServicePayload] = []
    delivery_radius_km: float
    pin_confirmed: bool
    distance_km: Optional[float] = None
    created_at: str
    updated_at: str
