# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Wire-format models for seller endpoints.

These sit on the boundary between the API and the DB; the DB stores
address columns flat and these models expose them as a nested
`address` object.
"""

import re
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.schemas.address import AddressPayload
from app.schemas.services import ServicePayload

# Same pattern as the payments change-request payload. Declared locally rather
# than imported so the registration schema does not depend on CR internals.
_UPI_VPA_RE = re.compile(r"^[A-Za-z0-9._-]{2,64}@[A-Za-z][A-Za-z0-9.-]{1,64}$")


def _validate_optional_vpa(v: Optional[str]) -> Optional[str]:
    if v is None or v == "":
        return None
    if not _UPI_VPA_RE.match(v):
        raise ValueError("upi_vpa format invalid")
    return v


class SellerRegisterBody(BaseModel):
    signup_token: str
    # Bounded to defeat email-header injection / unbounded subject growth via
    # `business_name` / `full_name` flowing into rendered email subjects.
    full_name: str = Field(min_length=1, max_length=120)
    business_name: str = Field(min_length=1, max_length=120)
    service_ids: list[int] = Field(min_length=1)
    address: AddressPayload
    gst_number: Optional[str] = None
    fssai_license: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_ifsc: Optional[str] = None
    # Optional: a seller without their UPI ID to hand must still be able to
    # finish signup. "Required" means required to ACCEPT UPI, not to register.
    upi_vpa: Optional[str] = None
    accept_policies: bool = False
    # "Keep me signed in on this device" — trusted long-term session when true.
    remember: bool = False
    # Present when the wizard was entered from a referral invite link; binds
    # referral attribution to the created seller. Optional + best-effort.
    referral_invite_token: Optional[str] = None

    @field_validator("upi_vpa")
    @classmethod
    def _upi_vpa(cls, v: Optional[str]) -> Optional[str]:
        return _validate_optional_vpa(v)

class SellerPhoneOtpRequestBody(BaseModel):
    email_token: str
    phone: str


class SellerPhoneOtpVerifyBody(BaseModel):
    email_token: str
    phone: str
    code: str


class SellerSelfPhoneOtpRequestBody(BaseModel):
    """Logged-in seller requests an OTP to a NEW phone they want to switch to."""

    phone: str


class SellerSelfPhoneOtpVerifyBody(BaseModel):
    """Logged-in seller submits the OTP sent to the new phone."""

    phone: str
    code: str


class SellerProfileUpdateBody(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=120)
    business_name: str = Field(min_length=1, max_length=120)
    service_ids: Optional[list[int]] = Field(default=None, min_length=1)
    address: AddressPayload
    phone: str
    gst_number: Optional[str] = None
    fssai_license: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_ifsc: Optional[str] = None
    upi_vpa: Optional[str] = None

    @field_validator("upi_vpa")
    @classmethod
    def _upi_vpa(cls, v: Optional[str]) -> Optional[str]:
        return _validate_optional_vpa(v)

class SellerProfilePayload(BaseModel):
    id: int
    user_id: int
    full_name: str
    business_name: str
    services: list[ServicePayload]
    address: AddressPayload
    phone: str
    gst_number: Optional[str] = None
    fssai_license: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_ifsc: Optional[str] = None
    upi_vpa: Optional[str] = None
    verification_status: str
    rejection_reason: Optional[str] = None
    avatar_url: Optional[str] = None


class SellerApplicationPayload(BaseModel):
    seller_id: int
    email: EmailStr
    full_name: Optional[str] = None
    business_name: str
    services: list[ServicePayload]
    address: AddressPayload
    phone: str
    gst_number: Optional[str] = None
    fssai_license: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_ifsc: Optional[str] = None
    upi_vpa: Optional[str] = None
    verification_status: str
    rejection_reason: Optional[str] = None
    submitted_at: Optional[str] = None
    updated_at: Optional[str] = None


class AdminSetServicesBody(BaseModel):
    service_ids: list[int] = Field(min_length=1)


class SetServiceDeliverySettingsBody(BaseModel):
    free_delivery_threshold: float = Field(ge=0, le=100000)
    delivery_fee: float = Field(ge=0, le=5000)
    # ETA is an optional partial update: omit both to leave the window
    # untouched, or send both to set it. Sending exactly one is rejected.
    delivery_eta_min_minutes: Optional[int] = Field(default=None, ge=1, le=20160)
    delivery_eta_max_minutes: Optional[int] = Field(default=None, ge=1, le=20160)
    pickup_enabled: Optional[bool] = None

    @model_validator(mode="after")
    def _check_window(self) -> "SetServiceDeliverySettingsBody":
        low, high = self.delivery_eta_min_minutes, self.delivery_eta_max_minutes
        if (low is None) != (high is None):
            raise ValueError("delivery_eta_min_minutes and delivery_eta_max_minutes must be set together")
        if low is not None and high is not None and low > high:
            raise ValueError("delivery_eta_min_minutes must be <= delivery_eta_max_minutes")
        return self


class OrderStatusCounts(BaseModel):
    delivered: int = 0
    packed: int = 0
    dispatched: int = 0
    pending: int = 0
    cancelled: int = 0
    paid: int = 0  # dormant OrderStatus value; captured so the donut total never under-reports


class InventoryServiceStat(BaseModel):
    service_id: int
    service_name: str
    in_stock: int
    total: int


class TopSubcategory(BaseModel):
    name: str
    count: int


class SellerMetricsRead(BaseModel):
    active_orders: int
    orders_today: int
    orders_this_month: int
    revenue_this_month: float
    revenue_last_month: float
    revenue_trend_pct: float
    total_products: int
    out_of_stock: int
    unavailable: int
    store_active: bool
    store_paused: bool = False
    is_premium: bool = False
    pin_confirmed: bool
    store_name: str
    order_status_counts: OrderStatusCounts
    inventory_by_service: list[InventoryServiceStat]
    top_subcategory: TopSubcategory | None = None


class RevenueSeriesPoint(BaseModel):
    date: str  # "YYYY-MM-DD" (IST calendar day)
    gov: float


class RevenueSeriesRead(BaseModel):
    points: list[RevenueSeriesPoint]
    avg_per_day: float
    peak: float
