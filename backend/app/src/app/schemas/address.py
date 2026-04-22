"""Pydantic schema for the structured address wire format.

Used as the nested `address` object on every API request/response body
that carries a seller or store address. The DB stores these fields as
flat columns (see `app.models.address.AddressBase`); the converters at
the bottom translate between the two shapes.
"""

import re
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.core.indian_states import INDIAN_STATES

_INDIA_PINCODE_RE = re.compile(r"^[1-9]\d{5}$")
_NON_INDIA_PINCODE_RE = re.compile(r"^[A-Za-z0-9\- ]{3,10}$")


class AddressPayload(BaseModel):
    address_line1: str = Field(min_length=1, max_length=120)
    address_line2: Optional[str] = Field(default=None, max_length=120)
    landmark: Optional[str] = Field(default=None, max_length=120)
    city: str = Field(min_length=1, max_length=80)
    state: str = Field(min_length=1, max_length=80)
    pincode: str = Field(min_length=3, max_length=10)
    country: str = Field(default="India", min_length=1, max_length=60)
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)

    @model_validator(mode="after")
    def _check_country_specific_rules(self) -> "AddressPayload":
        if self.country == "India":
            if not _INDIA_PINCODE_RE.match(self.pincode):
                raise ValueError(
                    "pincode must be 6 digits with no leading zero for India"
                )
            if self.state not in INDIAN_STATES:
                raise ValueError("state must be an Indian state or Union Territory")
        else:
            if not _NON_INDIA_PINCODE_RE.match(self.pincode):
                raise ValueError("pincode must be 3-10 alphanumeric characters")
        return self


_ADDRESS_FIELDS: tuple[str, ...] = (
    "address_line1",
    "address_line2",
    "landmark",
    "city",
    "state",
    "pincode",
    "country",
    "latitude",
    "longitude",
)


def address_from_payload(payload: AddressPayload) -> dict[str, object]:
    """Flatten the nested payload to the column names used on owner tables."""
    return {field: getattr(payload, field) for field in _ADDRESS_FIELDS}


def address_to_payload(owner: object) -> AddressPayload:
    """Build a nested payload from an owner object carrying the flat columns."""
    return AddressPayload(**{field: getattr(owner, field) for field in _ADDRESS_FIELDS})
