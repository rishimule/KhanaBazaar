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
from meilisearch_python_sdk.models.search import SearchParams
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.locale import get_request_locale
from app.core.redis import get_redis
from app.db.session import get_db_session
from app.models.address import Address
from app.models.catalog import (
    Category,
    CategoryTranslation,
    MasterProduct,
    MasterProductTranslation,
    Service,
    ServiceTranslation,
    Subcategory,
    SubcategoryTranslation,
)
from app.models.profile import SellerProfileService
from app.models.search_log import SearchQueryLog
from app.models.store import Store, StoreInventory
from app.schemas.search import (
    BrowseCategory,
    BrowseProductCard,
    BrowseResponse,
    BrowseSubcategory,
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
from app.search.locality import get_serviceable_store_ids, grid_cell_key

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
_browse_rate = _rate_limit("SEARCH_RATE_LIMIT_BROWSE_PER_MIN")


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
    q: str = Query(..., min_length=1, max_length=100),
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
    store_id: Optional[int] = Query(None, ge=1),
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


# ── /products ──────────────────────────────────────────────────────────────


_SORT_MAP: dict[str, Optional[list[str]]] = {
    "relevance": None,
    "price_asc": ["min_price:asc"],
    "price_desc": ["min_price:desc"],
    "distance": None,  # post-sort
}


@router.get(
    "/products",
    response_model=ProductsResponse,
    dependencies=[Depends(_products_rate)],
)
async def products(
    response: Response,
    request: Request,
    q: str = Query("", max_length=100),
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
    store_id: Optional[int] = Query(None),
    service_id: Optional[int] = Query(None),
    category_id: Optional[int] = Query(None),
    subcategory_id: Optional[int] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    sort: str = Query("relevance"),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=60),
    locale: str = Depends(get_request_locale),
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
) -> ProductsResponse:
    if sort not in _SORT_MAP:
        raise HTTPException(status_code=400, detail="invalid_sort")
    q = q.strip()
    if len(q) > 100:
        raise HTTPException(status_code=400, detail="q_too_long")

    if store_id is not None:
        serviceable: Optional[list[int]] = [store_id]
    else:
        serviceable = await get_serviceable_store_ids(session, redis, lat, lng)

    filters: list[str] = ["is_active = true"]
    if serviceable is not None and serviceable:
        ids_str = ",".join(str(s) for s in serviceable)
        filters.append(f"store_ids IN [{ids_str}]")
    if service_id is not None:
        filters.append(f"service_id = {service_id}")
    if category_id is not None:
        filters.append(f"category_id = {category_id}")
    if subcategory_id is not None:
        filters.append(f"subcategory_id = {subcategory_id}")
    if min_price is not None:
        filters.append(f"min_price >= {min_price}")
    if max_price is not None:
        filters.append(f"max_price <= {max_price}")

    client = get_meili_client()
    res = await client.index("products").search(
        q,
        filter=" AND ".join(filters),
        sort=_SORT_MAP[sort],
        offset=(page - 1) * page_size,
        limit=page_size,
        facets=["service_id", "category_id"],
    )

    serviceable_set: Optional[set[int]] = (
        set(serviceable) if serviceable is not None else None
    )

    cards: list[ProductCard] = []
    for hit in res.hits:
        offers: list[PerStoreOffer] = []
        for o in hit.get("per_store_offers", []):
            try:
                store_doc = await client.index("stores").get_document(o["store_id"])
                store_name = store_doc.get("name", f"Store {o['store_id']}")
                s_lat = store_doc.get("lat")
                s_lng = store_doc.get("lng")
            except Exception:
                store_name = f"Store {o['store_id']}"
                s_lat = s_lng = None
            distance = None
            if lat is not None and lng is not None and s_lat and s_lng:
                distance = round(_haversine_km(lat, lng, s_lat, s_lng), 2)
            offers.append(
                PerStoreOffer(
                    store_id=o["store_id"],
                    store_name=store_name,
                    price=float(o["price"]),
                    stock=int(o["stock"]),
                    is_available=bool(o["is_available"]),
                    is_serviceable=(
                        serviceable_set is None or o["store_id"] in serviceable_set
                    ),
                    store_paused=bool(o.get("store_paused", False)),
                    distance_km=distance,
                )
            )
        cards.append(
            ProductCard(
                id=hit["id"],
                slug=hit["slug"],
                name=hit.get(f"name_{locale}") or hit.get("name_en") or hit["slug"],
                image_url=hit.get("image_url"),
                brand=hit.get("brand"),
                unit=hit.get("unit"),
                service_id=hit["service_id"],
                category_id=hit["category_id"],
                subcategory_id=hit["subcategory_id"],
                min_price=float(hit.get("min_price", 0.0)),
                max_price=float(hit.get("max_price", 0.0)),
                in_stock_anywhere=bool(hit.get("in_stock_anywhere", False)),
                per_store_offers=offers,
            )
        )

    if sort == "distance":
        cards.sort(
            key=lambda c: min(
                (o.distance_km for o in c.per_store_offers if o.distance_km is not None),
                default=float("inf"),
            )
        )

    # Derived price bucket facet
    buckets = {"0_50": 0, "50_100": 0, "100_200": 0, "200_plus": 0}
    for c in cards:
        if c.min_price < 50:
            buckets["0_50"] += 1
        elif c.min_price < 100:
            buckets["50_100"] += 1
        elif c.min_price < 200:
            buckets["100_200"] += 1
        else:
            buckets["200_plus"] += 1

    facet_dist = res.facet_distribution or {}
    facets = FacetBuckets(
        service_id={str(k): int(v) for k, v in (facet_dist.get("service_id") or {}).items()},
        category_id={str(k): int(v) for k, v in (facet_dist.get("category_id") or {}).items()},
        min_price_bucket=buckets,
    )

    applied: dict[str, int | float | str] = {}
    if service_id is not None:
        applied["service_id"] = service_id
    if category_id is not None:
        applied["category_id"] = category_id
    if store_id is not None:
        applied["store_id"] = store_id
    if min_price is not None:
        applied["min_price"] = min_price
    if max_price is not None:
        applied["max_price"] = max_price

    query_id = str(uuid.uuid4())
    response.headers["X-Search-Query-ID"] = query_id

    total = int(res.estimated_total_hits or len(cards))
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
            result_count=total,
        )
    except Exception:
        pass

    return ProductsResponse(
        query_id=uuid.UUID(query_id),
        query=q,
        total=total,
        page=page,
        page_size=page_size,
        products=cards,
        facets=facets,
        applied_filters=applied,
        sort=sort,
    )


# ── /browse (per-service category carousels) ────────────────────────────────


_BROWSE_CARD_ATTRS = [
    "id",
    "slug",
    "image_url",
    "brand",
    "unit",
    "min_price",
    "max_price",
    "in_stock_anywhere",
    "category_id",
]


@router.get(
    "/browse",
    response_model=BrowseResponse,
    dependencies=[Depends(_browse_rate)],
)
async def browse(
    service_id: int = Query(..., ge=1),
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
    per_category: int = Query(12, ge=1, le=24),
    locale: str = Depends(get_request_locale),
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
) -> BrowseResponse:
    serviceable = await get_serviceable_store_ids(session, redis, lat, lng)
    cell = (
        grid_cell_key(lat, lng) if lat is not None and lng is not None else "no-loc"
    )
    cache_key = f"browse:{service_id}:{cell}:{locale}:{per_category}"
    cached = await redis.get(cache_key)
    if cached is not None:
        return BrowseResponse(**json.loads(cached))

    svc = (
        await session.execute(select(Service).where(Service.id == service_id))
    ).scalar_one_or_none()
    if svc is None:
        raise HTTPException(status_code=404, detail="service_not_found")
    svc_t = (
        await session.execute(
            select(ServiceTranslation).where(
                ServiceTranslation.service_id == service_id,
                ServiceTranslation.language_code == locale,
            )
        )
    ).scalar_one_or_none()
    if svc_t is None:
        svc_t = (
            await session.execute(
                select(ServiceTranslation).where(
                    ServiceTranslation.service_id == service_id,
                    ServiceTranslation.language_code == "en",
                )
            )
        ).scalar_one_or_none()
    svc_name = svc_t.name if svc_t else svc.slug

    # Location set but no store delivers here → nothing to show (distinct from
    # `serviceable is None`, which means no/invalid location → show everything).
    if serviceable is not None and not serviceable:
        body = BrowseResponse(
            service_id=service_id, service_name=svc_name, categories=[]
        )
        await redis.set(
            cache_key,
            body.model_dump_json(),
            ex=settings.SEARCH_BROWSE_CACHE_TTL_SECONDS,
        )
        return body

    cat_rows = (
        await session.execute(
            select(Category)
            .where(Category.service_id == service_id, Category.is_active.is_(True))
            .order_by(Category.sort_order, Category.id)
        )
    ).scalars().all()

    # Resolve localized category names (fallback to en, then slug).
    cat_names: dict[int, str] = {}
    for cat in cat_rows:
        ct = (
            await session.execute(
                select(CategoryTranslation).where(
                    CategoryTranslation.category_id == cat.id,
                    CategoryTranslation.language_code == locale,
                )
            )
        ).scalar_one_or_none()
        if ct is None:
            ct = (
                await session.execute(
                    select(CategoryTranslation).where(
                        CategoryTranslation.category_id == cat.id,
                        CategoryTranslation.language_code == "en",
                    )
                )
            ).scalar_one_or_none()
        cat_names[cat.id] = ct.name if ct else cat.slug

    serviceable_clause = ""
    if serviceable is not None and serviceable:
        ids_str = ",".join(str(s) for s in serviceable)
        serviceable_clause = f" AND store_ids IN [{ids_str}]"

    client = get_meili_client()
    queries = [
        SearchParams(
            index_uid="products",
            query="",
            filter=(
                f"is_active = true AND service_id = {service_id} "
                f"AND category_id = {cat.id}{serviceable_clause}"
            ),
            limit=per_category,
            facets=["subcategory_id"],
            attributes_to_retrieve=_BROWSE_CARD_ATTRS + [f"name_{locale}", "name_en"],
        )
        for cat in cat_rows
    ]

    # First pass: collect cards + the subcategory ids that actually have
    # in-area products (from the facet distribution, which counts the full
    # match set — not just the returned sample).
    pending: list[tuple[Category, list[BrowseProductCard], list[int]]] = []
    all_sub_ids: set[int] = set()
    if queries:
        results = await client.multi_search(queries)
        # multi_search preserves query order → align with cat_rows
        for cat, res in zip(cat_rows, results, strict=True):
            cards: list[BrowseProductCard] = []
            for hit in res.hits:
                cards.append(
                    BrowseProductCard(
                        id=hit["id"],
                        slug=hit["slug"],
                        name=hit.get(f"name_{locale}")
                        or hit.get("name_en")
                        or hit["slug"],
                        image_url=hit.get("image_url"),
                        brand=hit.get("brand"),
                        unit=hit.get("unit"),
                        min_price=float(hit.get("min_price", 0.0)),
                        max_price=float(hit.get("max_price", 0.0)),
                        in_stock_anywhere=bool(hit.get("in_stock_anywhere", False)),
                        category_id=hit["category_id"],
                    )
                )
            if not cards:
                continue
            facet = res.facet_distribution or {}
            sub_dist = facet.get("subcategory_id") or {}
            sub_ids = [int(k) for k, count in sub_dist.items() if count]
            all_sub_ids.update(sub_ids)
            pending.append((cat, cards, sub_ids))

    # Resolve subcategory metadata (slug, sort_order, localized name) in bulk.
    sub_meta: dict[int, tuple[str, int]] = {}
    sub_names: dict[int, str] = {}
    if all_sub_ids:
        for sub in (
            await session.execute(
                select(Subcategory).where(Subcategory.id.in_(all_sub_ids))
            )
        ).scalars():
            sub_meta[sub.id] = (sub.slug, sub.sort_order)
        for sid in all_sub_ids:
            st = (
                await session.execute(
                    select(SubcategoryTranslation).where(
                        SubcategoryTranslation.subcategory_id == sid,
                        SubcategoryTranslation.language_code == locale,
                    )
                )
            ).scalar_one_or_none()
            if st is None:
                st = (
                    await session.execute(
                        select(SubcategoryTranslation).where(
                            SubcategoryTranslation.subcategory_id == sid,
                            SubcategoryTranslation.language_code == "en",
                        )
                    )
                ).scalar_one_or_none()
            sub_names[sid] = st.name if st else sub_meta.get(sid, ("", 0))[0]

    categories: list[BrowseCategory] = []
    for cat, cards, sub_ids in pending:
        subs = [
            BrowseSubcategory(id=sid, slug=sub_meta[sid][0], name=sub_names[sid])
            for sid in sub_ids
            if sid in sub_meta
        ]
        subs.sort(key=lambda b: (sub_meta[b.id][1], b.id))
        categories.append(
            BrowseCategory(
                id=cat.id,
                slug=cat.slug,
                name=cat_names[cat.id],
                subcategories=subs,
                products=cards,
            )
        )

    body = BrowseResponse(
        service_id=service_id, service_name=svc_name, categories=categories
    )
    await redis.set(
        cache_key,
        body.model_dump_json(),
        ex=settings.SEARCH_BROWSE_CACHE_TTL_SECONDS,
    )
    return body


# ── /products/{id}/stores (comparison) ─────────────────────────────────────


@router.get(
    "/products/{master_product_id}/stores",
    response_model=CompareResponse,
)
async def compare_offers(
    master_product_id: int,
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
    locale: str = Depends(get_request_locale),
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
) -> CompareResponse:
    product = (
        await session.execute(
            select(MasterProduct).where(MasterProduct.id == master_product_id)
        )
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="product_not_found")

    translation = (
        await session.execute(
            select(MasterProductTranslation).where(
                MasterProductTranslation.master_product_id == master_product_id,
                MasterProductTranslation.language_code == locale,
            )
        )
    ).scalar_one_or_none()
    if translation is None:
        translation = (
            await session.execute(
                select(MasterProductTranslation).where(
                    MasterProductTranslation.master_product_id == master_product_id,
                    MasterProductTranslation.language_code == "en",
                )
            )
        ).scalar_one_or_none()

    subcat = (
        await session.execute(
            select(Subcategory).where(Subcategory.id == product.subcategory_id)
        )
    ).scalar_one()
    cat = (
        await session.execute(select(Category).where(Category.id == subcat.category_id))
    ).scalar_one()
    svc = (
        await session.execute(select(Service).where(Service.id == cat.service_id))
    ).scalar_one()
    svc_t = (
        await session.execute(
            select(ServiceTranslation).where(
                ServiceTranslation.service_id == svc.id,
                ServiceTranslation.language_code == locale,
            )
        )
    ).scalar_one_or_none()
    if svc_t is None:
        svc_t = (
            await session.execute(
                select(ServiceTranslation).where(
                    ServiceTranslation.service_id == svc.id,
                    ServiceTranslation.language_code == "en",
                )
            )
        ).scalar_one_or_none()
    svc_name = svc_t.name if svc_t else svc.slug

    rows = (
        await session.execute(
            select(StoreInventory, Store, Address)
            .join(Store, Store.id == StoreInventory.store_id)
            .join(Address, Address.id == Store.address_id)
            .where(
                StoreInventory.product_id == master_product_id,
                Store.is_active.is_(True),
            )
        )
    ).all()

    serviceable: Optional[list[int]] = None
    if lat is not None and lng is not None:
        serviceable = await get_serviceable_store_ids(session, redis, lat, lng)

    # Seller profiles that have THIS product's service paused, so a per-service
    # pause (not just a store-wide one) flags the offer as closed — mirrors
    # build_product_document so the compare view matches the results grid.
    paused_profile_ids = {
        pid
        for (pid,) in (
            await session.execute(
                select(SellerProfileService.seller_profile_id).where(
                    SellerProfileService.service_id == svc.id,
                    SellerProfileService.is_paused.is_(True),
                )
            )
        ).all()
    }

    offers: list[CompareOffer] = []
    pso_for_card: list[PerStoreOffer] = []
    for inv, store, address in rows:
        dist = None
        if (
            lat is not None
            and lng is not None
            and address.latitude is not None
            and address.longitude is not None
        ):
            dist = round(
                _haversine_km(lat, lng, address.latitude, address.longitude), 2
            )
        is_serv = serviceable is None or store.id in (serviceable or [])
        store_paused = bool(store.is_paused) or store.seller_profile_id in paused_profile_ids
        offers.append(
            CompareOffer(
                store=CompareStore(
                    id=store.id,
                    name=store.name,
                    lat=float(address.latitude) if address.latitude is not None else None,
                    lng=float(address.longitude) if address.longitude is not None else None,
                    distance_km=dist,
                    delivery_radius_km=float(store.delivery_radius_km),
                ),
                inventory_id=inv.id,
                price=float(inv.price),
                stock=int(inv.stock),
                is_available=bool(inv.is_available),
                is_serviceable=is_serv,
                store_paused=store_paused,
            )
        )
        pso_for_card.append(
            PerStoreOffer(
                store_id=store.id,
                store_name=store.name,
                inventory_id=inv.id,
                price=float(inv.price),
                stock=int(inv.stock),
                is_available=bool(inv.is_available),
                is_serviceable=is_serv,
                store_paused=store_paused,
                distance_km=dist,
            )
        )

    offers.sort(key=lambda o: o.price)

    card = ProductCard(
        id=product.id,
        slug=product.slug,
        name=translation.name if translation else product.slug,
        image_url=product.image_url,
        brand=product.brand,
        unit=product.unit,
        service_id=cat.service_id,
        service_name=svc_name,
        category_id=cat.id,
        subcategory_id=subcat.id,
        min_price=min((o.price for o in offers), default=float(product.base_price)),
        max_price=max((o.price for o in offers), default=float(product.base_price)),
        in_stock_anywhere=any(o.stock > 0 and o.is_available for o in offers),
        per_store_offers=pso_for_card,
    )

    return CompareResponse(product=card, offers=offers)


# ── /stores (search by name) ───────────────────────────────────────────────


@router.get("/stores", response_model=StoreSearchResponse)
async def stores_search(
    q: str = Query(..., min_length=1, max_length=100),
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=60),
) -> StoreSearchResponse:
    client = get_meili_client()
    res = await client.index("stores").search(
        q.strip(),
        filter="is_active = true",
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    items: list[SuggestStore] = []
    for h in res.hits:
        dist = None
        if lat is not None and lng is not None and h.get("lat") and h.get("lng"):
            dist = round(_haversine_km(lat, lng, h["lat"], h["lng"]), 2)
        items.append(
            SuggestStore(
                id=h["id"],
                name=h["name"],
                service_ids=h.get("service_ids", []),
                distance_km=dist,
            )
        )
    return StoreSearchResponse(
        total=int(res.estimated_total_hits or len(items)),
        page=page,
        page_size=page_size,
        stores=items,
    )


# ── /click (analytics) ─────────────────────────────────────────────────────


@router.post("/click", status_code=204)
async def click(
    payload: ClickPayload,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    row = (
        await session.execute(
            select(SearchQueryLog).where(SearchQueryLog.query_id == payload.query_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return Response(status_code=204)
    row.clicked_product_id = payload.clicked_product_id
    row.clicked_store_id = payload.clicked_store_id
    row.clicked_position = payload.position
    await session.commit()
    return Response(status_code=204)
