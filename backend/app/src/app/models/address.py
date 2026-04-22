"""Shared address columns applied as a mixin on owner tables.

The 9 columns mirror the `AddressPayload` Pydantic schema. Validation
for incoming wire-format data lives on the schema; this mixin only
defines DB column nullability. Owner tables inherit this mixin
alongside `BaseSchema`.
"""

from typing import Optional

from sqlmodel import Field, SQLModel


class AddressBase(SQLModel):
    address_line1: str = Field(nullable=False, max_length=120)
    address_line2: Optional[str] = Field(default=None, nullable=True, max_length=120)
    landmark: Optional[str] = Field(default=None, nullable=True, max_length=120)
    city: str = Field(nullable=False, max_length=80)
    state: str = Field(nullable=False, max_length=80)
    pincode: str = Field(nullable=False, max_length=10)
    country: str = Field(nullable=False, default="India", max_length=60)
    latitude: Optional[float] = Field(default=None, nullable=True)
    longitude: Optional[float] = Field(default=None, nullable=True)
