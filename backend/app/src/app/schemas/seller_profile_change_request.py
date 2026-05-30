# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Per-group Pydantic schemas for seller profile change requests.

Each profile group (identity, address, legal, banking, services,
store_basics) has a dedicated payload model with its own validators.
The :func:`validate_group_payload` helper looks up the right model and
returns a canonical JSON-ready dict — used by the service layer when
storing proposed/applied snapshots on the change-request row.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.otp import InvalidPhoneNumber, normalize_phone
from app.models.seller_profile_change_request import (
    SellerProfileChangeEventKind,
    SellerProfileChangeGroup,
    SellerProfileChangeStatus,
)
from app.schemas.address import AddressPayload

_GST_RE = re.compile(r"^[0-9A-Z]{15}$")
_FSSAI_RE = re.compile(r"^[0-9]{14}$")
_IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
_BANK_ACCOUNT_RE = re.compile(r"^[0-9]{9,18}$")


def _opt_match(value: Optional[str], pattern: re.Pattern[str], label: str) -> Optional[str]:
    if value is None or value == "":
        return None
    if not pattern.match(value):
        raise ValueError(f"{label} format invalid")
    return value


class IdentityPayload(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    business_name: str = Field(min_length=1, max_length=200)
    phone: str

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        try:
            return normalize_phone(v)
        except InvalidPhoneNumber:
            raise ValueError("phone format invalid") from None


class LegalPayload(BaseModel):
    gst_number: Optional[str] = None
    fssai_license: Optional[str] = None

    @field_validator("gst_number")
    @classmethod
    def _gst(cls, v: Optional[str]) -> Optional[str]:
        return _opt_match(v, _GST_RE, "gst_number")

    @field_validator("fssai_license")
    @classmethod
    def _fssai(cls, v: Optional[str]) -> Optional[str]:
        return _opt_match(v, _FSSAI_RE, "fssai_license")


class BankingPayload(BaseModel):
    bank_account_number: Optional[str] = None
    bank_ifsc: Optional[str] = None

    @field_validator("bank_account_number")
    @classmethod
    def _acct(cls, v: Optional[str]) -> Optional[str]:
        return _opt_match(v, _BANK_ACCOUNT_RE, "bank_account_number")

    @field_validator("bank_ifsc")
    @classmethod
    def _ifsc(cls, v: Optional[str]) -> Optional[str]:
        return _opt_match(v, _IFSC_RE, "bank_ifsc")


class ServiceRowPayload(BaseModel):
    service_id: int
    min_order_value: float = Field(ge=0.0, le=100000.0)


class ServicesPayload(BaseModel):
    services: list[ServiceRowPayload] = Field(min_length=1, max_length=20)

    @field_validator("services")
    @classmethod
    def _unique(cls, v: list[ServiceRowPayload]) -> list[ServiceRowPayload]:
        ids = [row.service_id for row in v]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate service_id rows")
        return v


class StoreBasicsPayload(BaseModel):
    delivery_radius_km: float = Field(gt=0.0, le=50.0)
    # Accepted optionally for older clients; current FE omits it (no rename UI).
    store_name: Optional[str] = Field(default=None, min_length=1, max_length=120)


# Discriminated union: each group has its own payload schema.
class ChangeRequestCreateBody(BaseModel):
    group: SellerProfileChangeGroup
    proposed: dict[str, Any]
    note: Optional[str] = Field(default=None, max_length=300)


class ChangeRequestResubmitBody(BaseModel):
    proposed: dict[str, Any]
    note: Optional[str] = Field(default=None, max_length=300)


class ChangeRequestApproveBody(BaseModel):
    applied: Optional[dict[str, Any]] = None
    note: Optional[str] = Field(default=None, max_length=500)


class ChangeRequestNoteBody(BaseModel):
    note: str = Field(min_length=5, max_length=500)


class ChangeRequestRejectBody(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class ChangeRequestEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: SellerProfileChangeEventKind
    actor_user_id: int
    actor_role: str
    payload_json: Optional[dict[str, Any]] = None
    note: Optional[str] = None
    created_at: datetime


class AdminQueueRow(BaseModel):
    """One row of the cross-seller change-request triage queue."""
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    seller_profile_id: int
    seller_user_id: int
    seller_business_name: str
    group: SellerProfileChangeGroup
    status: SellerProfileChangeStatus
    submission_count: int
    created_at: datetime
    updated_at: datetime


class ChangeRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    seller_profile_id: int
    group: SellerProfileChangeGroup
    status: SellerProfileChangeStatus
    proposed_json: dict[str, Any]
    applied_json: Optional[dict[str, Any]] = None
    baseline_json: dict[str, Any]
    admin_note: Optional[str] = None
    submission_count: int
    created_at: datetime
    updated_at: datetime
    decided_at: Optional[datetime] = None
    decided_by_user_id: Optional[int] = None
    events: list[ChangeRequestEventRead] = Field(default_factory=list)


# Group → Pydantic class lookup for runtime validation in the service layer.
GROUP_PAYLOAD_SCHEMA: dict[SellerProfileChangeGroup, type[BaseModel]] = {
    SellerProfileChangeGroup.Identity: IdentityPayload,
    SellerProfileChangeGroup.Address: AddressPayload,
    SellerProfileChangeGroup.Legal: LegalPayload,
    SellerProfileChangeGroup.Banking: BankingPayload,
    SellerProfileChangeGroup.Services: ServicesPayload,
    SellerProfileChangeGroup.StoreBasics: StoreBasicsPayload,
}


def validate_group_payload(
    group: SellerProfileChangeGroup, payload: dict[str, Any]
) -> dict[str, Any]:
    """Validate a payload against the group's schema; return the canonical dict."""
    cls = GROUP_PAYLOAD_SCHEMA[group]
    return cls.model_validate(payload).model_dump(mode="json")
