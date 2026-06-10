# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Request + response schemas for the admin catalog router.

Public catalog reads still use the schemas in `api/catalog.py` and
`schemas/services.py`. Admin endpoints return entity-specific Read models
wrapped in `PagedResponse` so the frontend table can show "page N of M".
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class TranslationOut(BaseModel):
    language_code: str
    name: str
    description: Optional[str] = None


class ProductImageRead(BaseModel):
    id: int
    url: str
    source: str
    position: int


class ProductImageUrlCreate(BaseModel):
    url: str


class ProductImageReorder(BaseModel):
    image_ids: List[int]


class ServiceAdminRead(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    slug: str
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    is_active: bool
    sort_order: int
    child_count: int = 0
    translations: List[TranslationOut] = Field(default_factory=list)


class CategoryAdminRead(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    service_id: int
    slug: str
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    is_active: bool
    sort_order: int
    child_count: int = 0
    translations: List[TranslationOut] = Field(default_factory=list)


class SubcategoryAdminRead(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    category_id: int
    slug: str
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    is_active: bool
    sort_order: int
    child_count: int = 0
    translations: List[TranslationOut] = Field(default_factory=list)


class ProductAdminRead(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    subcategory_id: int
    slug: str
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    base_price: float
    brand: Optional[str] = None
    unit: Optional[str] = None
    is_active: bool
    images: List[ProductImageRead] = Field(default_factory=list)
    translations: List[TranslationOut] = Field(default_factory=list)


class ServiceCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    sort_order: int = 0


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class CategoryAdminCreate(BaseModel):
    service_id: int
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    sort_order: int = 0


class CategoryAdminUpdate(BaseModel):
    service_id: Optional[int] = None
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class SubcategoryCreate(BaseModel):
    category_id: int
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    sort_order: int = 0


class SubcategoryUpdate(BaseModel):
    category_id: Optional[int] = None
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class ProductAdminCreate(BaseModel):
    subcategory_id: int
    name: str
    slug: Optional[str] = None
    description: str = ""
    image_url: Optional[str] = None
    base_price: float
    brand: Optional[str] = None
    unit: Optional[str] = None


class ProductAdminUpdate(BaseModel):
    subcategory_id: Optional[int] = None
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    base_price: Optional[float] = None
    brand: Optional[str] = None
    unit: Optional[str] = None
    is_active: Optional[bool] = None


class TranslationUpsert(BaseModel):
    language_code: str
    name: str = ""
    description: Optional[str] = None
