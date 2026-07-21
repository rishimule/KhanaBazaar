# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import enum
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import DateTime, Field, SQLModel


class UserRole(str, enum.Enum):
    Customer = "customer"
    Seller = "seller"
    Admin = "admin"


class AccountStatus(str, enum.Enum):
    # Lowercase member NAMES so the native PG enum stores lowercase values
    # (matches CreditAccountStatus; no values_callable needed).
    active = "active"
    deactivated = "deactivated"
    suspended = "suspended"
    deleted = "deleted"


class BaseSchema(SQLModel):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(  # type: ignore[call-overload]
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )
    updated_at: datetime = Field(  # type: ignore[call-overload]
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )


class UserBase(SQLModel):
    email: str = Field(index=True, unique=True, nullable=False)
    hashed_password: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True, nullable=False)
    role: UserRole = Field(default=UserRole.Customer, nullable=False)
    preferred_language: str = Field(default="en", foreign_key="language.code", nullable=False)


class User(BaseSchema, UserBase, table=True):
    account_status: AccountStatus = Field(
        default=AccountStatus.active, nullable=False, index=True
    )
    status_changed_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )
    status_reason: Optional[str] = Field(default=None, max_length=500)
    status_changed_by_user_id: Optional[int] = Field(
        default=None, foreign_key="user.id"
    )
