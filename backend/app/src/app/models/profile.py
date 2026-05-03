import enum
from datetime import date
from typing import Optional

from sqlmodel import Field, Relationship, UniqueConstraint

from app.models.address import Address
from app.models.base import BaseSchema, User


class VerificationStatus(str, enum.Enum):
    Pending = "pending"
    Approved = "approved"
    Rejected = "rejected"


class CustomerProfile(BaseSchema, table=True):
    __table_args__ = (
        UniqueConstraint("user_id", name="ix_customerprofile_user"),
        UniqueConstraint("phone", name="ix_customerprofile_phone"),
    )
    user_id: int = Field(foreign_key="user.id", nullable=False)
    first_name: str = Field(nullable=False)
    last_name: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None, max_length=20)
    date_of_birth: Optional[date] = Field(default=None)
    gender: Optional[str] = Field(default=None)

    user: User = Relationship()


class CustomerAddress(BaseSchema, table=True):
    __tablename__ = "customeraddress"
    __table_args__ = (
        UniqueConstraint("customer_profile_id", "address_id", name="uq_customeraddress_customer_address"),
    )
    customer_profile_id: int = Field(foreign_key="customerprofile.id", nullable=False, index=True)
    address_id: int = Field(foreign_key="address.id", nullable=False)
    label: Optional[str] = Field(default=None)
    is_default: bool = Field(default=False, nullable=False)

    customer_profile: CustomerProfile = Relationship()
    address: Address = Relationship()


class AdminProfile(BaseSchema, table=True):
    __table_args__ = (
        UniqueConstraint("user_id", name="ix_adminprofile_user"),
        UniqueConstraint("phone", name="ix_adminprofile_phone"),
    )
    user_id: int = Field(foreign_key="user.id", nullable=False)
    first_name: str = Field(nullable=False)
    last_name: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None, max_length=20)
    employee_code: Optional[str] = Field(default=None, unique=True)
    department: Optional[str] = Field(default=None)

    user: User = Relationship()


class SellerProfile(BaseSchema, table=True):
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_sellerprofile_user"),
        UniqueConstraint("phone", name="ix_sellerprofile_phone"),
    )
    user_id: int = Field(foreign_key="user.id", nullable=False)
    first_name: str = Field(nullable=False)
    last_name: Optional[str] = Field(default=None)
    phone: str = Field(nullable=False, max_length=20)
    business_name: str = Field(nullable=False)
    gst_number: Optional[str] = Field(default=None)
    fssai_license: Optional[str] = Field(default=None)
    bank_account_number: str = Field(nullable=False)
    bank_ifsc: str = Field(nullable=False)
    verification_status: VerificationStatus = Field(default=VerificationStatus.Pending, nullable=False)
    rejection_reason: Optional[str] = Field(default=None)
    business_address_id: int = Field(foreign_key="address.id", nullable=False, index=True)

    user: User = Relationship()
    business_address: Address = Relationship()


class SellerProfileService(BaseSchema, table=True):
    __tablename__ = "sellerprofile_service"
    __table_args__ = (
        UniqueConstraint(
            "seller_profile_id", "service_id", name="uq_sellerprofile_service"
        ),
    )
    seller_profile_id: int = Field(
        foreign_key="sellerprofile.id", nullable=False, index=True
    )
    service_id: int = Field(
        foreign_key="service.id", nullable=False, index=True
    )
