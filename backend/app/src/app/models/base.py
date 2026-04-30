import enum
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import DateTime, Field, SQLModel


class UserRole(str, enum.Enum):
    Customer = "customer"
    Seller = "seller"
    Admin = "admin"


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
    pass
