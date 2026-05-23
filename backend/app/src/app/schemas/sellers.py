# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Wire-format models for seller endpoints.

These sit on the boundary between the API and the DB; the DB stores
address columns flat and these models expose them as a nested
`address` object.
"""

from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.schemas.address import AddressPayload
from app.schemas.services import ServicePayload


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


class SellerPhoneOtpRequestBody(BaseModel):
    email_token: str
    phone: str


class SellerPhoneOtpVerifyBody(BaseModel):
    email_token: str
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
    verification_status: str
    rejection_reason: Optional[str] = None


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
    verification_status: str
    rejection_reason: Optional[str] = None
    submitted_at: Optional[str] = None
    updated_at: Optional[str] = None


class AdminSetServicesBody(BaseModel):
    service_ids: list[int] = Field(min_length=1)


class SellerMetricsRead(BaseModel):
    active_orders: int
    orders_today: int
    orders_this_month: int
    revenue_this_month: float
    total_products: int
    out_of_stock: int
    unavailable: int
    store_active: bool
    pin_confirmed: bool
