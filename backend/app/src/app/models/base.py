import enum
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import DateTime, Field, SQLModel


class UserRole(str, enum.Enum):
    Customer = "customer"
    Seller = "seller"
    Admin = "admin"

class BaseSchema(SQLModel):
    """Base schema for all models to inherit from."""
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True)
    )

class UserBase(SQLModel):
    email: str = Field(index=True, unique=True, nullable=False)
    is_active: bool = Field(default=True)
    role: UserRole = Field(default=UserRole.Customer)
    full_name: Optional[str] = Field(default=None)

class User(BaseSchema, UserBase, table=True):
    pass

class ItemBase(SQLModel):
    title: str = Field(index=True, nullable=False)
    description: Optional[str] = Field(default=None)
    owner_id: int = Field(foreign_key="user.id", nullable=False)

class Item(BaseSchema, ItemBase, table=True):
    pass
