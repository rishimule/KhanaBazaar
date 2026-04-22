"""Wire-format models for seller endpoints.

These sit on the boundary between the API and the DB; the DB stores
address columns flat and these models expose them as a nested
`address` object.
"""

from typing import Optional

from pydantic import BaseModel, EmailStr

from app.schemas.address import AddressPayload


class SellerRegisterBody(BaseModel):
    email_token: str
    full_name: str
    phone: str
    business_name: str
    business_category: str
    address: AddressPayload
    gst_number: str
    fssai_license: str
    bank_account_number: str
    bank_ifsc: str


class SellerProfileUpdateBody(BaseModel):
    business_name: str
    business_category: str
    address: AddressPayload
    phone: str
    gst_number: str
    fssai_license: str
    bank_account_number: str
    bank_ifsc: str


class SellerProfilePayload(BaseModel):
    id: int
    user_id: int
    business_name: str
    business_category: str
    address: AddressPayload
    phone: str
    gst_number: str
    fssai_license: str
    bank_account_number: str
    bank_ifsc: str
    verification_status: str
    rejection_reason: Optional[str] = None


class SellerApplicationPayload(BaseModel):
    seller_id: int
    email: EmailStr
    full_name: Optional[str] = None
    business_name: str
    business_category: str
    address: AddressPayload
    phone: str
    gst_number: str
    fssai_license: str
    bank_account_number: str
    bank_ifsc: str
    verification_status: str
    rejection_reason: Optional[str] = None
    submitted_at: Optional[str] = None
    updated_at: Optional[str] = None
