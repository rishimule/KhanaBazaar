from typing import List

from sqlmodel import Field, Relationship, UniqueConstraint

from app.models.address import AddressBase
from app.models.base import BaseSchema, User
from app.models.catalog import MasterProduct


class Store(BaseSchema, AddressBase, table=True):
    name: str = Field(index=True, nullable=False)
    is_active: bool = Field(default=True)
    seller_id: int = Field(foreign_key="user.id", nullable=False)

    # Relationships
    seller: User = Relationship()
    inventories: List["StoreInventory"] = Relationship(back_populates="store")


class StoreInventory(BaseSchema, table=True):
    __table_args__ = (
        UniqueConstraint("store_id", "product_id", name="uq_store_product"),
    )
    store_id: int = Field(foreign_key="store.id", nullable=False)
    product_id: int = Field(foreign_key="masterproduct.id", nullable=False)
    price: float = Field(nullable=False)
    stock: int = Field(default=0, nullable=False)
    is_available: bool = Field(default=True)

    # Relationships
    store: Store = Relationship(back_populates="inventories")
    product: MasterProduct = Relationship(back_populates="inventories")
