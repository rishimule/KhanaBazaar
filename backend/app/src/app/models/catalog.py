import enum
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel, UniqueConstraint

from app.models.base import BaseSchema


class LanguageCode(str, enum.Enum):
    English = "en"
    Hindi = "hi"
    Marathi = "mr"
    Gujarati = "gu"
    Punjabi = "pa"


class Language(SQLModel, table=True):
    code: str = Field(primary_key=True)
    name: str = Field(nullable=False)
    native_name: str = Field(nullable=False)
    is_active: bool = Field(default=True, nullable=False)


class Service(BaseSchema, table=True):
    slug: str = Field(nullable=False, unique=True, index=True)
    icon_url: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True, nullable=False)
    sort_order: int = Field(default=0, nullable=False)


class ServiceTranslation(BaseSchema, table=True):
    __tablename__ = "service_translation"
    __table_args__ = (UniqueConstraint("service_id", "language_code", name="uq_service_translation"),)
    service_id: int = Field(foreign_key="service.id", nullable=False)
    language_code: str = Field(foreign_key="language.code", nullable=False)
    name: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)


class Category(BaseSchema, table=True):
    __table_args__ = (UniqueConstraint("service_id", "slug", name="uq_category_service_slug"),)
    service_id: int = Field(foreign_key="service.id", nullable=False, index=True)
    slug: str = Field(nullable=False)
    sort_order: int = Field(default=0, nullable=False)

    service: Service = Relationship()


class CategoryTranslation(BaseSchema, table=True):
    __tablename__ = "category_translation"
    __table_args__ = (UniqueConstraint("category_id", "language_code", name="uq_category_translation"),)
    category_id: int = Field(foreign_key="category.id", nullable=False)
    language_code: str = Field(foreign_key="language.code", nullable=False)
    name: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)


class Subcategory(BaseSchema, table=True):
    __table_args__ = (UniqueConstraint("category_id", "slug", name="uq_subcategory_category_slug"),)
    category_id: int = Field(foreign_key="category.id", nullable=False, index=True)
    slug: str = Field(nullable=False)
    sort_order: int = Field(default=0, nullable=False)


class SubcategoryTranslation(BaseSchema, table=True):
    __tablename__ = "subcategory_translation"
    __table_args__ = (UniqueConstraint("subcategory_id", "language_code", name="uq_subcategory_translation"),)
    subcategory_id: int = Field(foreign_key="subcategory.id", nullable=False)
    language_code: str = Field(foreign_key="language.code", nullable=False)
    name: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)


class MasterProduct(BaseSchema, table=True):
    subcategory_id: int = Field(foreign_key="subcategory.id", nullable=False, index=True)
    slug: str = Field(nullable=False, unique=True, index=True)
    image_url: Optional[str] = Field(default=None)
    base_price: float = Field(nullable=False)


class MasterProductTranslation(BaseSchema, table=True):
    __tablename__ = "masterproduct_translation"
    __table_args__ = (UniqueConstraint("master_product_id", "language_code", name="uq_masterproduct_translation"),)
    master_product_id: int = Field(foreign_key="masterproduct.id", nullable=False)
    language_code: str = Field(foreign_key="language.code", nullable=False)
    name: str = Field(nullable=False)
    description: str = Field(nullable=False)
