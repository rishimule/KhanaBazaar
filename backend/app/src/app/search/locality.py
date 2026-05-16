# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""PostGIS-driven serviceable-store lookup with a Redis grid cache."""
from __future__ import annotations

import json
import math
from typing import Optional

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings

_GRID_DEG = 0.005  # ~500 m at India latitudes
_INDIA_BBOX = (6.5, 36.0, 68.0, 98.0)  # lat_min, lat_max, lng_min, lng_max


def grid_cell_key(lat: float, lng: float) -> str:
    lat_cell = math.floor(lat / _GRID_DEG) * _GRID_DEG
    lng_cell = math.floor(lng / _GRID_DEG) * _GRID_DEG
    return f"serviceable:{lat_cell:.4f}:{lng_cell:.4f}"


def in_india_bbox(lat: float, lng: float) -> bool:
    return (
        _INDIA_BBOX[0] <= lat <= _INDIA_BBOX[1]
        and _INDIA_BBOX[2] <= lng <= _INDIA_BBOX[3]
    )


async def get_serviceable_store_ids(
    session: AsyncSession,
    redis: aioredis.Redis,
    lat: Optional[float],
    lng: Optional[float],
) -> Optional[list[int]]:
    """Return store IDs that can deliver to (lat,lng). None = locality disabled."""
    if lat is None or lng is None:
        return None
    if not in_india_bbox(lat, lng):
        return None

    key = grid_cell_key(lat, lng)
    cached = await redis.get(key)
    if cached is not None:
        return json.loads(cached)

    rows = (
        await session.execute(
            text(
                """
                SELECT s.id
                FROM store s
                JOIN address a ON a.id = s.address_id
                WHERE s.is_active
                  AND a.geo IS NOT NULL
                  AND ST_DWithin(
                    a.geo,
                    ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
                    s.delivery_radius_km * 1000
                  )
                """
            ),
            {"lat": lat, "lng": lng},
        )
    ).all()
    ids = [row[0] for row in rows]
    await redis.set(
        key, json.dumps(ids), ex=settings.SEARCH_SERVICEABLE_GRID_TTL_SECONDS
    )
    return ids
