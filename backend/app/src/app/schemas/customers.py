# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.catalog import LanguageCode
from app.schemas.address import AddressPayload


class CustomerAddressRead(BaseModel):
    id: int
    label: str | None
    is_default: bool
    address: AddressPayload


class CustomerProfileRead(BaseModel):
    user_id: int
    email: str
    first_name: str
    last_name: str | None
    phone: str | None
    date_of_birth: date | None = None
    preferred_language: str | None = None
    marketing_opt_in: bool = False
    notify_order_email: bool = True
    notify_order_sms: bool = False
    phone_verified_at: datetime | None = None
    addresses: list[CustomerAddressRead]


class CustomerProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, max_length=20)
    date_of_birth: date | None = None

    @model_validator(mode="after")
    def _first_name_cannot_be_null(self) -> "CustomerProfileUpdate":
        if "first_name" in self.model_fields_set and self.first_name is None:
            raise ValueError("first_name cannot be null")
        return self


class CustomerPreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_language: LanguageCode | None = None
    marketing_opt_in: bool | None = None
    notify_order_email: bool | None = None
    notify_order_sms: bool | None = None


class CustomerAddressWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, max_length=60)
    is_default: bool = False
    address: AddressPayload
