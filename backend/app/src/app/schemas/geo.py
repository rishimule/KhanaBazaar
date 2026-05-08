"""Pydantic schemas for /api/v1/geo/* endpoints."""
from typing import List, Optional

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


class ServiceabilityResponse(BaseModel):
    serviceable: bool
    store_count: Optional[int] = None
