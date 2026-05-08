"""Geo proxy + serviceability endpoints. All public (no auth).

Server-side proxy hides the Google Maps API key. Per-IP rate-limit + Redis
cache reduce upstream cost.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.google_maps import (
    GoogleMapsClient,
    GoogleMapsError,
    autocomplete,
    place_details,
    reverse_geocode,
)
from app.core.rate_limit import incr_with_ttl
from app.core.redis import get_redis
from app.db.session import get_db_session
from app.schemas.geo import (
    AutocompleteResponse,
    GeoComponent,
    GeoPlace,
    GeoPrediction,
    ServiceabilityRequest,
    ServiceabilityResponse,
)

router = APIRouter()


def _get_client() -> GoogleMapsClient:
    if not settings.GOOGLE_MAPS_SERVER_API_KEY:
        raise HTTPException(status_code=503, detail="geo provider not configured")
    return GoogleMapsClient(api_key=settings.GOOGLE_MAPS_SERVER_API_KEY)


async def _geo_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    redis = await get_redis()
    count = await incr_with_ttl(redis, f"rl:geo:{ip}", ttl=60)
    if count > settings.GEO_RATE_LIMIT_PER_MIN:
        raise HTTPException(status_code=429, detail="rate limit exceeded")


async def _cache_get(cache_key: str) -> Optional[dict[str, Any]]:
    redis = await get_redis()
    raw = await redis.get(cache_key)
    return json.loads(raw) if raw else None


async def _cache_set(cache_key: str, value: dict[str, Any], ttl: int) -> None:
    redis = await get_redis()
    await redis.setex(cache_key, ttl, json.dumps(value))


def _to_geo_place(p: Any) -> GeoPlace:
    return GeoPlace(
        place_id=p.place_id,
        formatted_address=p.formatted_address,
        latitude=p.latitude,
        longitude=p.longitude,
        components=[
            GeoComponent(
                long_name=c.long_name,
                short_name=c.short_name,
                types=list(c.types),
            )
            for c in p.components
        ],
    )


@router.get("/autocomplete", response_model=AutocompleteResponse,
            dependencies=[Depends(_geo_rate_limit)])
async def autocomplete_endpoint(
    q: str = Query(min_length=1, max_length=200),
    session_token: str = Query(min_length=1, max_length=64),
) -> AutocompleteResponse:
    cache_key = f"geo:auto:{session_token}:{q.lower().strip()}"
    cached = await _cache_get(cache_key)
    if cached:
        return AutocompleteResponse(**cached)

    client = _get_client()
    try:
        preds = await autocomplete(client, query=q, session_token=session_token)
    except GoogleMapsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        await client.aclose()

    response = AutocompleteResponse(
        predictions=[
            GeoPrediction(place_id=p.place_id, description=p.description)
            for p in preds
        ]
    )
    await _cache_set(
        cache_key,
        response.model_dump(),
        settings.GEO_AUTOCOMPLETE_CACHE_TTL_SECONDS,
    )
    return response


@router.get("/place/{place_id}", response_model=GeoPlace,
            dependencies=[Depends(_geo_rate_limit)])
async def place_endpoint(
    place_id: str,
    session_token: str = Query(min_length=1, max_length=64),
) -> GeoPlace:
    client = _get_client()
    try:
        place = await place_details(
            client, place_id=place_id, session_token=session_token
        )
    except GoogleMapsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        await client.aclose()
    return _to_geo_place(place)


@router.get("/reverse", response_model=GeoPlace,
            dependencies=[Depends(_geo_rate_limit)])
async def reverse_endpoint(
    lat: float = Query(ge=-90.0, le=90.0),
    lng: float = Query(ge=-180.0, le=180.0),
) -> GeoPlace:
    cache_key = f"geo:rev:{round(lat, 4)}:{round(lng, 4)}"
    cached = await _cache_get(cache_key)
    if cached:
        return GeoPlace(**cached)

    client = _get_client()
    try:
        place = await reverse_geocode(client, lat=lat, lng=lng)
    except GoogleMapsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        await client.aclose()

    out = _to_geo_place(place)
    await _cache_set(
        cache_key,
        out.model_dump(),
        settings.GEO_REVERSE_CACHE_TTL_SECONDS,
    )
    return out


@router.post("/serviceability", response_model=ServiceabilityResponse,
             dependencies=[Depends(_geo_rate_limit)])
async def serviceability_endpoint(
    body: ServiceabilityRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ServiceabilityResponse:
    if body.store_id is not None:
        sql = text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM store s "
            "  JOIN address a ON a.id = s.address_id "
            "  WHERE s.id = :store_id AND s.is_active "
            "    AND a.geo IS NOT NULL "
            "    AND ST_DWithin("
            "      a.geo, "
            "      ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, "
            "      s.delivery_radius_km * 1000"
            "    )"
            ") AS ok"
        )
        result = await session.exec(  # type: ignore[call-overload]
            sql.bindparams(lat=body.lat, lng=body.lng, store_id=body.store_id)
        )
        ok = bool(result.scalar_one())
        return ServiceabilityResponse(serviceable=ok)

    sql = text(
        "SELECT COUNT(*) FROM store s "
        "JOIN address a ON a.id = s.address_id "
        "WHERE s.is_active AND a.geo IS NOT NULL "
        "  AND ST_DWithin("
        "    a.geo, "
        "    ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, "
        "    s.delivery_radius_km * 1000"
        "  )"
    )
    result = await session.exec(  # type: ignore[call-overload]
        sql.bindparams(lat=body.lat, lng=body.lng)
    )
    count = int(result.scalar_one())
    return ServiceabilityResponse(serviceable=count > 0, store_count=count)
