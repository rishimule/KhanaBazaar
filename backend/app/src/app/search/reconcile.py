# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Deterministic shard-rotated Postgres↔Meilisearch reconciler.

Public entrypoints (called from the Celery task):

    reconcile_products(session, client) -> ReconcileSummary
    reconcile_stores(session, client)   -> ReconcileSummary

Both follow the same shape:
    1. Drain the DLQ → enqueue per-id reindex tasks for those ids.
    2. Cheap pass: compare counts + max(db_updated_at) via Meili stats +
       a sort-desc search of size 1. If clean, return.
    3. Deep pass: for today's shard, diff DB rows ↔ Meili docs in both
       directions; enqueue reindex tasks for missing / modified ids and
       deletion tasks for Meili-extra ids.
    4. Persist a JSON summary in Redis under `search:reconcile:last:{kind}`.

The diff math (`diff_shard`) is a pure function and is unit-tested in
isolation. Orchestration ships in a follow-up commit.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, cast

import redis

from app.core.config import settings

SHARDS = 24
BATCH = 500
MEILI_PAGE = 1000
DELTA_CAP_FRACTION = 0.10
STATE_KEY_TEMPLATE = "search:reconcile:last:{kind}"
ABORT_KEY_TEMPLATE = "search:reconcile:abort:{kind}"

COMPARE_FIELDS_PRODUCT: tuple[str, ...] = (
    "name_en", "name_hi", "name_mr", "name_gu", "name_pa",
    "brand", "is_active", "min_price", "max_price",
    "in_stock_anywhere", "service_id", "category_id",
    "subcategory_id", "store_ids", "db_updated_at",
)
COMPARE_FIELDS_STORE: tuple[str, ...] = (
    "name", "service_ids", "lat", "lng",
    "delivery_radius_km", "is_active", "db_updated_at",
)


@dataclass
class ShardDeltas:
    missing: list[int] = field(default_factory=list)
    modified: list[int] = field(default_factory=list)
    extra: list[int] = field(default_factory=list)


@dataclass
class ReconcileSummary:
    kind: str
    started_at: float
    finished_at: float
    mode: str
    shard: int | None
    deltas: ShardDeltas
    dlq_drained: int
    error: str | None = None


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def diff_shard(
    db_docs: Mapping[int, Mapping[str, Any]],
    meili_docs: Mapping[int, Mapping[str, Any]],
    compare_fields: Iterable[str],
) -> ShardDeltas:
    """Partition two id→doc maps into (missing in Meili, modified, extra in Meili).

    `modified` only fires on a field that lives in `compare_fields`. Fields
    like `image_url` or per-store offer churn are intentionally excluded so
    that frequent steady-state writes don't trigger spurious re-syncs.
    """
    deltas = ShardDeltas()
    fields_t = tuple(compare_fields)
    for id_, db_doc in db_docs.items():
        meili_doc = meili_docs.get(id_)
        if meili_doc is None:
            deltas.missing.append(id_)
            continue
        for f in fields_t:
            if db_doc.get(f) != meili_doc.get(f):
                deltas.modified.append(id_)
                break
    for id_ in meili_docs.keys() - db_docs.keys():
        deltas.extra.append(id_)
    deltas.missing.sort()
    deltas.modified.sort()
    deltas.extra.sort()
    return deltas


def current_shard(now: float | None = None) -> int:
    """Today's shard derived from the current UTC hour. Cycles every 24 hours."""
    t = now if now is not None else time.time()
    return int(t // 3600) % SHARDS


def total_deltas(deltas: ShardDeltas) -> int:
    return len(deltas.missing) + len(deltas.modified) + len(deltas.extra)


def write_summary(client: redis.Redis, summary: ReconcileSummary) -> None:
    key = STATE_KEY_TEMPLATE.format(kind=summary.kind)
    payload = asdict(summary)
    payload["deltas"] = asdict(summary.deltas)
    client.set(key, json.dumps(payload))


def read_summary(client: redis.Redis, kind: str) -> dict[str, Any] | None:
    raw = client.get(STATE_KEY_TEMPLATE.format(kind=kind))
    if raw is None:
        return None
    return cast(dict[str, Any], json.loads(cast(bytes, raw)))
