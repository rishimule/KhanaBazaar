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
    full_name: str
    business_name: str
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
    full_name: Optional[str] = None
    business_name: str
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
