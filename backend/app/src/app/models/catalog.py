# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
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
    is_active: bool = Field(default=True, nullable=False, index=True)
    sort_order: int = Field(default=0, nullable=False)


class ServiceTranslation(BaseSchema, table=True):
    __tablename__ = "service_translation"
    __table_args__ = (UniqueConstraint("service_id", "language_code", name="uq_service_translation"),)
    service_id: int = Field(foreign_key="service.id", nullable=False)
    language_code: str = Field(foreign_key="language.code", nullable=False)
    name: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)


class Category(BaseSchema, table=True):
    # Partial unique on (service_id, slug) WHERE is_active applied in migration.
    service_id: int = Field(foreign_key="service.id", nullable=False, index=True)
    slug: str = Field(nullable=False)
    image_url: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True, nullable=False, index=True)
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
    # Partial unique on (category_id, slug) WHERE is_active applied in migration.
    category_id: int = Field(foreign_key="category.id", nullable=False, index=True)
    slug: str = Field(nullable=False)
    image_url: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True, nullable=False, index=True)
    sort_order: int = Field(default=0, nullable=False)


class SubcategoryTranslation(BaseSchema, table=True):
    __tablename__ = "subcategory_translation"
    __table_args__ = (UniqueConstraint("subcategory_id", "language_code", name="uq_subcategory_translation"),)
    subcategory_id: int = Field(foreign_key="subcategory.id", nullable=False)
    language_code: str = Field(foreign_key="language.code", nullable=False)
    name: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)


class MasterProduct(BaseSchema, table=True):
    # Partial unique on (subcategory_id, slug) WHERE is_active applied in migration.
    # Global slug unique constraint is dropped — slugs are unique within a subcategory only.
    subcategory_id: int = Field(foreign_key="subcategory.id", nullable=False, index=True)
    slug: str = Field(nullable=False, index=True)
    image_url: Optional[str] = Field(default=None)
    base_price: float = Field(nullable=False)
    brand: Optional[str] = Field(default=None)
    unit: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True, nullable=False, index=True)


class MasterProductTranslation(BaseSchema, table=True):
    __tablename__ = "masterproduct_translation"
    __table_args__ = (UniqueConstraint("master_product_id", "language_code", name="uq_masterproduct_translation"),)
    master_product_id: int = Field(foreign_key="masterproduct.id", nullable=False)
    language_code: str = Field(foreign_key="language.code", nullable=False)
    name: str = Field(nullable=False)
    description: str = Field(nullable=False)
