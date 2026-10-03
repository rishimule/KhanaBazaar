# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Pydantic schemas for /api/v1/geo/* endpoints."""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class GeoComponent(BaseModel):
    long_name: str
    short_name: str
    types: List[str]


class GeoPrediction(BaseModel):
    place_id: str
    description: str


class GeoPlace(BaseModel):
    place_id: str
    formatted_address: str
    latitude: float
    longitude: float
    components: List[GeoComponent] = []


class AutocompleteResponse(BaseModel):
    predictions: List[GeoPrediction]


class ServiceabilityRequest(BaseModel):
    lat: float = Field(ge=-90.0, le=90.0)
    lng: float = Field(ge=-180.0, le=180.0)
    store_id: Optional[int] = None
    # With store_id: courier counts only when THIS service can ship.
    service_id: Optional[int] = None


class ServiceabilityResponse(BaseModel):
    # Local door delivery only — unchanged meaning for existing callers.
    serviceable: bool
    store_count: Optional[int] = None
    # Set only when store_id was given (spec §12).
    zone: Optional[Literal["local", "courier", "none"]] = None
    courier_service_ids: list[int] = []
