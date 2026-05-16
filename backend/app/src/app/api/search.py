# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from __future__ import annotations

import hashlib
import json
import math
import uuid
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.locale import get_request_locale
from app.core.redis import get_redis
from app.db.session import get_db_session
from app.models.address import Address
from app.models.catalog import (
    Category,
    MasterProduct,
    MasterProductTranslation,
    Subcategory,
)
from app.models.search_log import SearchQueryLog
from app.models.store import Store, StoreInventory
from app.schemas.search import (
    ClickPayload,
    CompareOffer,
    CompareResponse,
    CompareStore,
    FacetBuckets,
    PerStoreOffer,
    ProductCard,
    ProductsResponse,
    StoreSearchResponse,
    SuggestProduct,
    SuggestResponse,
    SuggestStore,
    SuggestStoreOfferBest,
    SuggestTerm,
)
from app.search.client import get_meili_client
from app.search.locality import grid_cell_key, get_serviceable_store_ids

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


def _suggest_cache_key(
    q: str,
    lat: Optional[float],
    lng: Optional[float],
    store_id: Optional[int],
    locale: str,
) -> str:
    cell = (
        grid_cell_key(lat, lng) if lat is not None and lng is not None else "no-loc"
    )
    raw = f"{q}|{cell}|{store_id or 0}|{locale}"
    return "suggest:" + hashlib.sha1(raw.encode()).hexdigest()


# Rate-limit dependency factory ─────────────────────────────────────────────


def _rate_limit(setting_name: str):
    """Per-IP rate-limit dependency. Reuses Redis."""

    async def _check(
        request: Request, redis: aioredis.Redis = Depends(get_redis)
    ) -> None:
        ip = request.client.host if request.client else "anon"
        key = f"ratelim:search:{setting_name}:{ip}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
        cap = getattr(settings, setting_name)
        if count > cap:
            ttl = await redis.ttl(key)
            raise HTTPException(
                status_code=429,
                detail="rate_limited",
                headers={"Retry-After": str(max(1, ttl))},
            )

    return _check


_suggest_rate = _rate_limit("SEARCH_RATE_LIMIT_SUGGEST_PER_MIN")
_products_rate = _rate_limit("SEARCH_RATE_LIMIT_PRODUCTS_PER_MIN")


async def _log_query(
    session: AsyncSession,
    *,
    query_id: str,
    user_id: Optional[int],
    session_id: Optional[str],
    query: str,
    locale: str,
    lat: Optional[float],
    lng: Optional[float],
    store_id: Optional[int],
    result_count: int,
) -> None:
    def _round(v: Optional[float]) -> Optional[float]:
        return round(v, 3) if v is not None else None

    row = SearchQueryLog(
        query_id=uuid.UUID(query_id) if isinstance(query_id, str) else query_id,
        user_id=user_id,
        session_id=session_id,
        query=query[:100],
        locale=locale,
        lat=_round(lat),
        lng=_round(lng),
        store_id=store_id,
        result_count=result_count,
    )
    session.add(row)
    await session.commit()


# ── /suggest ───────────────────────────────────────────────────────────────


@router.get(
    "/suggest",
    response_model=SuggestResponse,
    dependencies=[Depends(_suggest_rate)],
)
async def suggest(
    response: Response,
    request: Request,
    q: str = Query(..., min_length=0, max_length=100),
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
    store_id: Optional[int] = Query(None),
    limit: int = Query(5, ge=1, le=10),
    locale: str = Depends(get_request_locale),
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
) -> SuggestResponse:
    q = q.strip()
    if not q:
        raise HTTPException(status_code=400, detail="q_required")
    if len(q) > 100:
        raise HTTPException(status_code=400, detail="q_too_long")

    cache_key = _suggest_cache_key(q, lat, lng, store_id, locale)
    cached = await redis.get(cache_key)
    if cached is not None:
        payload = json.loads(cached)
        response.headers["X-Search-Query-ID"] = payload["query_id"]
        return SuggestResponse(**payload)

    client = get_meili_client()

    # Resolve serviceable stores
    if store_id is not None:
        store_filter: Optional[list[int]] = [store_id]
    else:
        store_filter = await get_serviceable_store_ids(session, redis, lat, lng)

    products_filter_parts: list[str] = ["is_active = true"]
    if store_filter is not None and store_filter:
        ids = ",".join(str(s) for s in store_filter)
        products_filter_parts.append(f"store_ids IN [{ids}]")
    products_filter = " AND ".join(products_filter_parts)

    products_res = await client.index("products").search(
        q, limit=limit, filter=products_filter
    )
    terms_res = await client.index("search_terms").search(
        q, limit=limit, filter=f"locale = '{locale}'"
    )
    stores_res = await client.index("stores").search(
        q, limit=3, filter="is_active = true"
    )

    def _name_for_locale(doc: dict) -> str:
        return (
            doc.get(f"name_{locale}")
            or doc.get("name_en")
            or doc.get("slug", "")
        )

    products: list[SuggestProduct] = []
    for hit in products_res.hits:
        offers = [
            o
            for o in hit.get("per_store_offers", [])
            if store_filter is None or o["store_id"] in store_filter
        ]
        in_stock = [o for o in offers if o["is_available"] and o["stock"] > 0]
        best = (
            min(in_stock, key=lambda o: o["price"])
            if in_stock
            else (min(offers, key=lambda o: o["price"]) if offers else None)
        )
        best_store: Optional[SuggestStoreOfferBest] = None
        if best is not None:
            try:
                store_doc = await client.index("stores").get_document(best["store_id"])
                store_name = store_doc["name"]
            except Exception:
                store_name = f"Store {best['store_id']}"
            best_store = SuggestStoreOfferBest(
                id=best["store_id"],
                name=store_name,
                price=best["price"],
                is_available=best["is_available"] and best["stock"] > 0,
            )
        products.append(
            SuggestProduct(
                id=hit["id"],
                name=_name_for_locale(hit),
                image_url=hit.get("image_url"),
                min_price=float(hit.get("min_price", 0.0)),
                store_count=len(offers),
                best_store=best_store,
            )
        )

    stores: list[SuggestStore] = []
    for hit in stores_res.hits:
        dist = None
        if lat is not None and lng is not None and hit.get("lat") and hit.get("lng"):
            dist = round(_haversine_km(lat, lng, hit["lat"], hit["lng"]), 2)
        stores.append(
            SuggestStore(
                id=hit["id"],
                name=hit["name"],
                service_ids=hit.get("service_ids", []),
                distance_km=dist,
            )
        )

    terms = [
        SuggestTerm(text=h["term"], kind=h.get("kind", "product_name"))
        for h in terms_res.hits
    ]

    query_id = str(uuid.uuid4())
    body = SuggestResponse(
        query_id=uuid.UUID(query_id), terms=terms, products=products, stores=stores
    )
    await redis.set(
        cache_key,
        body.model_dump_json(),
        ex=settings.SEARCH_SUGGEST_CACHE_TTL_SECONDS,
    )
    response.headers["X-Search-Query-ID"] = query_id

    # Best-effort persistent log (do not block on errors)
    try:
        await _log_query(
            session,
            query_id=query_id,
            user_id=None,
            session_id=request.headers.get("X-Session-Id"),
            query=q,
            locale=locale,
            lat=lat,
            lng=lng,
            store_id=store_id,
            result_count=len(products),
        )
    except Exception:
        pass

    return body
