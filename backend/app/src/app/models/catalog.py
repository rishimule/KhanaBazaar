from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseSchema

if TYPE_CHECKING:
    from app.models.store import StoreInventory

class Category(BaseSchema, table=True):
    name: str = Field(unique=True, index=True, nullable=False)
    description: Optional[str] = Field(default=None)

    # Relationships
    products: List["MasterProduct"] = Relationship(back_populates="category")

class MasterProduct(BaseSchema, table=True):
    name: str = Field(index=True, nullable=False)
    description: str = Field(nullable=False)
    category_id: int = Field(foreign_key="category.id", nullable=False)
    image_url: Optional[str] = Field(default=None)
    base_price: float = Field(nullable=False)

    # Relationships
    category: Category = Relationship(back_populates="products")
    inventories: List["StoreInventory"] = Relationship(back_populates="product")
