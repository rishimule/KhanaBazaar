# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Which stores serve a point, cached per ~500 m grid cell in Redis.

The value is a `Locality` (local store ids, plus courier store ids per
service). The `v2` key prefix exists because v1 cached a bare list of local
ids: a deploy must never read that shape back (spec 2026-10-02 §12).
"""
from __future__ import annotations

import math
from typing import Optional

import redis.asyncio as aioredis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.services.serviceability import Locality, compute_locality, in_india_bbox

__all__ = ["get_locality", "get_serviceable_store_ids", "grid_cell_key", "in_india_bbox"]

_GRID_DEG = 0.005  # ~500 m at India latitudes
_KEY_PREFIX = "serviceable:v2"


def grid_cell_key(lat: float, lng: float) -> str:
    lat_cell = math.floor(lat / _GRID_DEG) * _GRID_DEG
    lng_cell = math.floor(lng / _GRID_DEG) * _GRID_DEG
    return f"{_KEY_PREFIX}:{lat_cell:.4f}:{lng_cell:.4f}"


async def get_locality(
    session: AsyncSession,
    redis: aioredis.Redis,
    lat: Optional[float],
    lng: Optional[float],
) -> Optional[Locality]:
    """The stores serving (lat, lng). None = no usable point (locality off)."""
    if lat is None or lng is None or not in_india_bbox(lat, lng):
        return None
    key = grid_cell_key(lat, lng)
    cached = await redis.get(key)
    if cached is not None:
        return Locality.from_json(cached)
    locality = await compute_locality(session, lat=lat, lng=lng)
    await redis.set(key, locality.to_json(), ex=settings.SEARCH_SERVICEABLE_GRID_TTL_SECONDS)
    return locality


async def get_serviceable_store_ids(
    session: AsyncSession,
    redis: aioredis.Redis,
    lat: Optional[float],
    lng: Optional[float],
) -> Optional[list[int]]:
    """Local (door-delivery) store ids only. None = locality disabled."""
    locality = await get_locality(session, redis, lat, lng)
    return None if locality is None else list(locality.local)
