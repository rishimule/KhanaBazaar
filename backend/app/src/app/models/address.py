import enum
from typing import Optional

from sqlalchemy import Column, Enum as SAEnum
from sqlmodel import Field

from app.models.base import BaseSchema


class LocationSource(str, enum.Enum):
    manual = "manual"
    autocomplete = "autocomplete"
    pin = "pin"
    geocoded = "geocoded"


class Address(BaseSchema, table=True):
    address_line1: str = Field(nullable=False, max_length=120)
    address_line2: Optional[str] = Field(default=None, nullable=True, max_length=120)
    landmark: Optional[str] = Field(default=None, nullable=True, max_length=120)
    city: str = Field(nullable=False, max_length=80)
    state: str = Field(nullable=False, max_length=80)
    pincode: str = Field(nullable=False, max_length=10)
    country: str = Field(nullable=False, default="India", max_length=60)
    latitude: Optional[float] = Field(default=None, nullable=True)
    longitude: Optional[float] = Field(default=None, nullable=True)
    digipin: Optional[str] = Field(default=None, nullable=True, max_length=12)
    place_id: Optional[str] = Field(default=None, nullable=True, max_length=255)
    location_source: Optional[LocationSource] = Field(
        default=None,
        sa_column=Column(
            SAEnum(LocationSource, name="locationsource"),
            nullable=True,
        ),
    )
    # Note: `geo` is a Postgres GENERATED column added in a separate migration.
    # SQLModel does not declare it; reads happen via raw SQL in the
    # store-listing query.
