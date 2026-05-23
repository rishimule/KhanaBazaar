# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
from datetime import datetime

from pydantic import BaseModel


class FavoriteIdsResponse(BaseModel):
    ids: list[int]


class FavoriteProductPreview(BaseModel):
    product_id: int
    name: str
    image_url: str | None
    category_id: int


class FavoriteAtStore(BaseModel):
    product_id: int
    name: str
    image_url: str | None
    category_id: int
    inventory_id: int
    price: float
    stock: int
    favourited_at: datetime


class StoreFavGroup(BaseModel):
    store_id: int
    store_name: str
    distance_km: float
    items: list[FavoriteAtStore]


class FavoritesGroupedResponse(BaseModel):
    groups: list[StoreFavGroup]
    unavailable: list[FavoriteProductPreview]


class FavoriteToggleResponse(BaseModel):
    favourited: bool
