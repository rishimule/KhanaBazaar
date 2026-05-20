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
from typing import Any, Awaitable, Callable, Iterable, Mapping, cast

import redis
from meilisearch_python_sdk import AsyncClient
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.catalog import MasterProduct
from app.models.store import Store
from app.search import dlq

SHARDS = 24
BATCH = 500
MEILI_PAGE = 1000
DELTA_CAP_FRACTION = 0.10
# Cap applies only above this floor — tiny catalogs (dev / staging) should
# still self-heal even when the delta ratio is large in relative terms.
DELTA_CAP_FLOOR = 100
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


# ─── Cheap pass ────────────────────────────────────────────────────────────


async def _count_real_docs(index: Any) -> int:
    """Count documents that are real catalog rows, not `_meta_v*` markers.

    Marker docs lack `is_active`, so a filter on it cleanly excludes them
    without us needing to track the marker count across schema versions.
    """
    hits = await index.search(
        "",
        filter="is_active IN [true, false]",
        limit=0,
    )
    if hits.total_hits is not None:
        return int(hits.total_hits)
    if hits.estimated_total_hits is not None:
        return int(hits.estimated_total_hits)
    return 0


async def _max_db_updated_at(index: Any) -> int:
    hits = await index.search(
        "",
        sort=["db_updated_at:desc"],
        limit=1,
        attributes_to_retrieve=["db_updated_at"],
    )
    return (
        int(hits.hits[0]["db_updated_at"])
        if hits.hits and "db_updated_at" in hits.hits[0]
        else 0
    )


async def _cheap_pass_products(
    session: AsyncSession, client: AsyncClient
) -> tuple[bool, int, int]:
    db_count, db_max_ts = (
        await session.execute(
            select(func.count(MasterProduct.id), func.max(MasterProduct.updated_at))
            .where(MasterProduct.is_active.is_(True))
        )
    ).one()
    db_max_ts_int = int(db_max_ts.timestamp()) if db_max_ts else 0

    index = client.index("products")
    meili_count = await _count_real_docs(index)
    meili_max_ts = await _max_db_updated_at(index)
    clean = (db_count - meili_count) == 0 and abs(db_max_ts_int - meili_max_ts) < 60
    return clean, db_count, meili_count


async def _cheap_pass_stores(
    session: AsyncSession, client: AsyncClient
) -> tuple[bool, int, int]:
    db_count, db_max_ts = (
        await session.execute(
            select(func.count(Store.id), func.max(Store.updated_at))
            .where(Store.is_active.is_(True))
        )
    ).one()
    db_max_ts_int = int(db_max_ts.timestamp()) if db_max_ts else 0

    index = client.index("stores")
    meili_count = await _count_real_docs(index)
    meili_max_ts = await _max_db_updated_at(index)
    clean = (db_count - meili_count) == 0 and abs(db_max_ts_int - meili_max_ts) < 60
    return clean, db_count, meili_count


# ─── Deep pass ─────────────────────────────────────────────────────────────


async def _fetch_meili_chunk(
    index: Any, ids: list[int], fields: tuple[str, ...]
) -> dict[int, dict[str, Any]]:
    """Fetch a batch of docs by id. Returns {id: doc}.

    Uses `filter='id IN [...]'` because the local Meili version we run
    does not accept an `ids` parameter on the documents/fetch endpoint.
    `id` must be in `filterableAttributes` for this to work.
    """
    if not ids:
        return {}
    filter_expr = f"id IN [{','.join(str(i) for i in ids)}]"
    page = await index.get_documents(
        fields=[*fields, "id"],
        filter=filter_expr,
        limit=len(ids),
    )
    out: dict[int, dict[str, Any]] = {}
    for d in page.results:
        try:
            out[int(d["id"])] = d
        except (TypeError, ValueError, KeyError):
            continue
    return out


async def _list_meili_ids_in_shard(
    index: Any, shard: int
) -> set[int]:
    """Page every Meili doc id, keep ones whose id % SHARDS == shard.

    Meili has no server-side modulo filter, so we paginate ids only
    (cheap) and partition in Python.
    """
    offset = 0
    keep: set[int] = set()
    while True:
        page = await index.get_documents(fields=["id"], limit=MEILI_PAGE, offset=offset)
        if not page.results:
            break
        for d in page.results:
            raw_id = d.get("id")
            try:
                meili_id = int(raw_id)
            except (TypeError, ValueError):
                # _meta_v* marker docs have non-numeric ids — skip.
                continue
            if meili_id % SHARDS == shard:
                keep.add(meili_id)
        if len(page.results) < MEILI_PAGE:
            break
        offset += MEILI_PAGE
    return keep


async def _deep_pass_products(
    session: AsyncSession, client: AsyncClient, shard: int
) -> ShardDeltas:
    from app.search.serialize import build_product_document

    index = client.index("products")
    deltas = ShardDeltas()

    # Match the cheap pass denominator: only walk active rows. Inactive
    # rows that linger in Meili will be flagged by the reverse pass as
    # `extra` (DB-active set excludes them) and get cleaned up.
    db_ids = [
        pid for (pid,) in (
            await session.execute(
                select(MasterProduct.id)
                .where(MasterProduct.id % SHARDS == shard)
                .where(MasterProduct.is_active.is_(True))
            )
        ).all()
    ]
    for chunk_start in range(0, len(db_ids), BATCH):
        chunk = db_ids[chunk_start : chunk_start + BATCH]
        meili_docs = await _fetch_meili_chunk(index, chunk, COMPARE_FIELDS_PRODUCT)
        db_docs: dict[int, dict[str, Any]] = {}
        for pid in chunk:
            doc = await build_product_document(session, pid)
            if doc is not None:
                db_docs[pid] = doc
        chunk_deltas = diff_shard(db_docs, meili_docs, COMPARE_FIELDS_PRODUCT)
        deltas.missing.extend(chunk_deltas.missing)
        deltas.modified.extend(chunk_deltas.modified)

    meili_in_shard = await _list_meili_ids_in_shard(index, shard)
    if meili_in_shard:
        db_alive = {
            pid for (pid,) in (
                await session.execute(
                    select(MasterProduct.id)
                    .where(MasterProduct.id.in_(meili_in_shard))
                    .where(MasterProduct.is_active.is_(True))
                )
            ).all()
        }
        deltas.extra.extend(sorted(meili_in_shard - db_alive))

    deltas.missing.sort()
    deltas.modified.sort()
    return deltas


async def _deep_pass_stores(
    session: AsyncSession, client: AsyncClient, shard: int
) -> ShardDeltas:
    from app.search.serialize import build_store_document

    index = client.index("stores")
    deltas = ShardDeltas()

    db_ids = [
        sid for (sid,) in (
            await session.execute(
                select(Store.id)
                .where(Store.id % SHARDS == shard)
                .where(Store.is_active.is_(True))
            )
        ).all()
    ]
    for chunk_start in range(0, len(db_ids), BATCH):
        chunk = db_ids[chunk_start : chunk_start + BATCH]
        meili_docs = await _fetch_meili_chunk(index, chunk, COMPARE_FIELDS_STORE)
        db_docs: dict[int, dict[str, Any]] = {}
        for sid in chunk:
            doc = await build_store_document(session, sid)
            if doc is not None:
                db_docs[sid] = doc
        chunk_deltas = diff_shard(db_docs, meili_docs, COMPARE_FIELDS_STORE)
        deltas.missing.extend(chunk_deltas.missing)
        deltas.modified.extend(chunk_deltas.modified)

    meili_in_shard = await _list_meili_ids_in_shard(index, shard)
    if meili_in_shard:
        db_alive = {
            sid for (sid,) in (
                await session.execute(
                    select(Store.id)
                    .where(Store.id.in_(meili_in_shard))
                    .where(Store.is_active.is_(True))
                )
            ).all()
        }
        deltas.extra.extend(sorted(meili_in_shard - db_alive))

    deltas.missing.sort()
    deltas.modified.sort()
    return deltas


# ─── Orchestration ─────────────────────────────────────────────────────────


def _enqueue_reindex(kind: str, ids: list[int]) -> None:
    # Late import: tasks.py imports reconcile (for the Celery wrapper), so
    # we'd otherwise create a circular import at module load time.
    from app.search.tasks import reindex_master_product, reindex_store

    task = reindex_master_product if kind == "product" else reindex_store
    for id_ in ids:
        task.delay(id_)


CheapPass = Callable[[AsyncSession, AsyncClient], Awaitable[tuple[bool, int, int]]]
DeepPass = Callable[[AsyncSession, AsyncClient, int], Awaitable[ShardDeltas]]


async def _reconcile(
    *,
    kind: str,
    session: AsyncSession,
    client: AsyncClient,
    cheap: CheapPass,
    deep: DeepPass,
    dlq_kind: dlq.DeadLetterKind,
    force_deep: bool,
) -> ReconcileSummary:
    started = time.time()
    r = _redis_client()

    if r.get(ABORT_KEY_TEMPLATE.format(kind=kind)) is not None:
        summary = ReconcileSummary(
            kind=kind,
            started_at=started,
            finished_at=time.time(),
            mode="aborted_held",
            shard=None,
            deltas=ShardDeltas(),
            dlq_drained=0,
            error="abort flag set",
        )
        write_summary(r, summary)
        return summary

    drained_ids = dlq.drain(dlq_kind)
    if drained_ids:
        _enqueue_reindex("product" if dlq_kind == "product" else "store", drained_ids)

    try:
        clean, db_count, _meili_count = await cheap(session, client)
    except Exception as exc:  # noqa: BLE001
        # Record the exception *class* only — `str(exc)` from asyncpg /
        # Meili / SQLAlchemy frequently embeds connection strings, host
        # info, or SQL fragments which would then surface through the
        # health endpoint.
        summary = ReconcileSummary(
            kind=kind,
            started_at=started,
            finished_at=time.time(),
            mode="cheap_failed",
            shard=None,
            deltas=ShardDeltas(),
            dlq_drained=len(drained_ids),
            error=type(exc).__name__,
        )
        write_summary(r, summary)
        raise

    if clean and not force_deep:
        summary = ReconcileSummary(
            kind=kind,
            started_at=started,
            finished_at=time.time(),
            mode="cheap_clean",
            shard=None,
            deltas=ShardDeltas(),
            dlq_drained=len(drained_ids),
        )
        write_summary(r, summary)
        return summary

    shard = current_shard()
    deltas = await deep(session, client, shard)

    cap = max(db_count * DELTA_CAP_FRACTION, DELTA_CAP_FLOOR)
    if db_count > 0 and total_deltas(deltas) > cap:
        r.set(ABORT_KEY_TEMPLATE.format(kind=kind), "1", ex=86400)
        summary = ReconcileSummary(
            kind=kind,
            started_at=started,
            finished_at=time.time(),
            mode="aborted_delta_cap",
            shard=shard,
            deltas=deltas,
            dlq_drained=len(drained_ids),
            error=f"delta {total_deltas(deltas)} exceeds {DELTA_CAP_FRACTION:.0%}",
        )
        write_summary(r, summary)
        return summary

    _enqueue_reindex(
        "product" if dlq_kind == "product" else "store",
        deltas.missing + deltas.modified + deltas.extra,
    )

    summary = ReconcileSummary(
        kind=kind,
        started_at=started,
        finished_at=time.time(),
        mode="deep",
        shard=shard,
        deltas=deltas,
        dlq_drained=len(drained_ids),
    )
    write_summary(r, summary)
    return summary


async def reconcile_products(
    session: AsyncSession,
    client: AsyncClient,
    *,
    force_deep: bool = False,
) -> ReconcileSummary:
    return await _reconcile(
        kind="product",
        session=session,
        client=client,
        cheap=_cheap_pass_products,
        deep=_deep_pass_products,
        dlq_kind=dlq.DEAD_LETTER_KIND_PRODUCT,
        force_deep=force_deep,
    )


async def reconcile_stores(
    session: AsyncSession,
    client: AsyncClient,
    *,
    force_deep: bool = False,
) -> ReconcileSummary:
    return await _reconcile(
        kind="store",
        session=session,
        client=client,
        cheap=_cheap_pass_stores,
        deep=_deep_pass_stores,
        dlq_kind=dlq.DEAD_LETTER_KIND_STORE,
        force_deep=force_deep,
    )
