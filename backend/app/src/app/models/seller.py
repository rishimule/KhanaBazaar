import enum
from typing import Optional

from sqlmodel import Field, Relationship

from app.models.address import AddressBase
from app.models.base import BaseSchema, User


class VerificationStatus(str, enum.Enum):
    Pending = "pending"
    Approved = "approved"
    Rejected = "rejected"


class SellerProfile(BaseSchema, AddressBase, table=True):
    user_id: int = Field(foreign_key="user.id", unique=True, nullable=False)
    business_name: str = Field(nullable=False)
    business_category: str = Field(nullable=False)
    phone: str = Field(nullable=False)
    gst_number: str = Field(nullable=False)
    fssai_license: str = Field(nullable=False)
    bank_account_number: str = Field(nullable=False)
    bank_ifsc: str = Field(nullable=False)
    verification_status: VerificationStatus = Field(default=VerificationStatus.Pending)
    rejection_reason: Optional[str] = Field(default=None)

    user: User = Relationship()
