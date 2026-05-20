# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from __future__ import annotations

import json
import logging
from typing import Any

import redis as sync_redis
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.indian_states import INDIAN_STATES
from app.db.session import get_db_session
from app.models.catalog import MasterProduct, MasterProductTranslation
from app.models.store import Store
from app.schemas.search_health import (
    IndexHealth,
    ReconcileSummaryOut,
    SearchHealthResponse,
    SearchTermsHealth,
)
from app.search import dlq
from app.search.client import get_meili_client
from app.search.reconcile import STATE_KEY_TEMPLATE

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe under the versioned API prefix.

    Mirrors the root `/health` route. Both are kept: the root path serves
    legacy uptime probes and load-balancer health checks; the versioned
    path lets API consumers verify reachability without crossing the API
    prefix boundary.
    """
    return {"status": "ok", "environment": settings.ENVIRONMENT}


@router.get("/indian-states")
async def get_indian_states() -> dict[str, list[str]]:
    return {"states": INDIAN_STATES}


_HEALTH_CACHE_KEY = "search:health:cached"
_HEALTH_CACHE_TTL_SECONDS = 30


def _sync_redis_client() -> sync_redis.Redis:
    return sync_redis.Redis.from_url(settings.REDIS_URL)


async def _gather_index_health(
    session: AsyncSession,
    kind: str,
    table: Any,
    dlq_kind: dlq.DeadLetterKind,
    meili_uid: str,
) -> IndexHealth:
    db_count, db_max = (
        await session.execute(
            select(func.count(table.id), func.max(table.updated_at)).where(
                table.is_active.is_(True)
            )
        )
    ).one()
    db_max_int = int(db_max.timestamp()) if db_max else 0

    meili_count = 0
    meili_max = 0
    unreachable = False
    try:
        client = get_meili_client()
        index = client.index(meili_uid)
        # Filter out `_meta_v*` marker docs by requiring is_active — only
        # real catalog rows have it.
        count_hits = await index.search(
            "",
            filter="is_active IN [true, false]",
            limit=0,
        )
        meili_count = int(
            count_hits.total_hits
            if count_hits.total_hits is not None
            else (count_hits.estimated_total_hits or 0)
        )
        max_hits = await index.search(
            "",
            sort=["db_updated_at:desc"],
            limit=1,
            attributes_to_retrieve=["db_updated_at"],
        )
        if max_hits.hits and "db_updated_at" in max_hits.hits[0]:
            meili_max = int(max_hits.hits[0]["db_updated_at"])
    except Exception as exc:  # noqa: BLE001
        unreachable = True
        logger.debug("search.health.meili_unreachable kind=%s err=%s", kind, exc)

    summary_raw = _sync_redis_client().get(STATE_KEY_TEMPLATE.format(kind=kind))
    summary: ReconcileSummaryOut | None = None
    if summary_raw is not None:
        try:
            d = json.loads(summary_raw)
            deltas = d.get("deltas") or {}
            summary = ReconcileSummaryOut(
                finished_at=d.get("finished_at"),
                mode=d.get("mode"),
                deltas={k: len(v) for k, v in deltas.items() if isinstance(v, list)},
                error=d.get("error"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("search.health.summary_parse_failed kind=%s err=%s", kind, exc)
            summary = None

    return IndexHealth(
        db_count=int(db_count or 0),
        meili_count=meili_count,
        db_max_updated_at=db_max_int,
        meili_max_db_updated_at=meili_max,
        lag_seconds=max(db_max_int - meili_max, 0),
        last_reconcile=summary,
        dlq_size=dlq.size(dlq_kind),
        meili_unreachable=unreachable,
    )


@router.get("/search-health", response_model=SearchHealthResponse)
async def search_health(
    session: AsyncSession = Depends(get_db_session),
) -> SearchHealthResponse:
    r = _sync_redis_client()
    cached = r.get(_HEALTH_CACHE_KEY)
    if cached is not None:
        return SearchHealthResponse.model_validate_json(cached)

    products = await _gather_index_health(
        session, "product", MasterProduct, dlq.DEAD_LETTER_KIND_PRODUCT, "products"
    )
    stores = await _gather_index_health(
        session, "store", Store, dlq.DEAD_LETTER_KIND_STORE, "stores"
    )

    db_term_count = (
        await session.execute(select(func.count(MasterProductTranslation.id)))
    ).scalar_one()
    meili_term_count = 0
    terms_unreachable = False
    try:
        st = await get_meili_client().index("search_terms").get_stats()
        meili_term_count = st.number_of_documents
    except Exception as exc:  # noqa: BLE001
        terms_unreachable = True
        logger.debug("search.health.terms_meili_unreachable err=%s", exc)

    body = SearchHealthResponse(
        products=products,
        stores=stores,
        search_terms=SearchTermsHealth(
            db_count=int(db_term_count or 0),
            meili_count=meili_term_count,
            meili_unreachable=terms_unreachable,
        ),
    )
    r.set(_HEALTH_CACHE_KEY, body.model_dump_json(), ex=_HEALTH_CACHE_TTL_SECONDS)
    return body
