# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Celery tasks that keep Meilisearch in sync with Postgres.

Each task wraps an async helper. The async helpers are also called directly by
the bulk reindex CLI and by tests, which is why they live as module-level
functions rather than inside the task bodies.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

import httpx
import redis
from celery import Task
from meilisearch_python_sdk.errors import MeilisearchApiError
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError

from app.core.celery_app import celery_app
from app.core.config import settings
from app.db.session import async_session_factory
from app.search import dlq
from app.search.client import get_meili_client
from app.search.serialize import (
    build_product_document,
    build_search_term_docs,
    build_store_document,
)

logger = logging.getLogger(__name__)

_sync_redis = redis.Redis.from_url(settings.REDIS_URL)

# Retry configuration shared by the per-id reindex tasks. Transient Meili 5xx,
# network errors, and connection resets all autoretry with exponential backoff
# up to ~5 minutes before the task hits max_retries and lands on the DLQ.
_REINDEX_AUTORETRY = (
    MeilisearchApiError,
    httpx.HTTPError,
    ConnectionError,
    # Transient asyncpg/SQLAlchemy errors that show up under concurrent
    # Celery worker fanout (shared engine, "another operation in progress").
    # Retrying after a short backoff lets the next attempt grab a fresh
    # connection from the pool.
    InterfaceError,
    OperationalError,
    DBAPIError,
)
_REINDEX_MAX_RETRIES = 5
_REINDEX_BACKOFF_MAX = 300


class _DLQTask(Task):
    """Celery base task that pushes the first positional arg onto a DLQ
    when retries are exhausted. Subclasses set `_dlq_kind` after task
    construction (Celery decorators don't pass kwargs to base.__init__)."""

    abstract = True
    _dlq_kind: dlq.DeadLetterKind | None = None

    def on_failure(self, exc: Any, task_id: Any, args: Any, kwargs: Any, einfo: Any) -> None:  # noqa: ANN401
        kind = self._dlq_kind
        if kind is None or not args:
            return
        try:
            dlq.push(kind, int(args[0]))
        except Exception:  # noqa: BLE001 — DLQ push must never escalate
            logger.exception("search.dlq.push_failed kind=%s args=%s", kind, args)


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from sync code, even when an event loop is active.

    Celery worker processes run sync code, so plain asyncio.run() works there.
    Eager mode inside an async test, however, already has a running loop —
    asyncio.run() would raise. Always offloading to a fresh thread covers both.
    """
    result: dict[str, Any] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001
            result["error"] = exc

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join(timeout=60)
    if "error" in result:
        raise result["error"]
    return result.get("value")


async def _do_reindex_product(product_id: int) -> None:
    async with async_session_factory() as session:
        doc = await build_product_document(session, product_id)
    client = get_meili_client()
    index = client.index("products")
    if doc is None:
        try:
            task = await index.delete_document(product_id)
            await client.wait_for_task(task.task_uid)
        except Exception as exc:  # noqa: BLE001
            logger.debug("search.delete_skip product_id=%s err=%s", product_id, exc)
    else:
        task = await index.add_documents([doc], primary_key="id")
        await client.wait_for_task(task.task_uid)


@celery_app.task(
    base=_DLQTask,
    bind=True,
    name="search.reindex_master_product",
    autoretry_for=_REINDEX_AUTORETRY,
    retry_backoff=True,
    retry_backoff_max=_REINDEX_BACKOFF_MAX,
    max_retries=_REINDEX_MAX_RETRIES,
)
def reindex_master_product(self: Task, product_id: int) -> None:  # noqa: ARG001
    lock = _sync_redis.lock(
        f"meili_sync:product:{product_id}", timeout=5, blocking_timeout=1
    )
    if not lock.acquire(blocking=False):
        logger.debug("search.sync.coalesced product_id=%s", product_id)
        return
    try:
        _run_async(_do_reindex_product(product_id))
    finally:
        try:
            lock.release()
        except Exception:
            pass


reindex_master_product._dlq_kind = dlq.DEAD_LETTER_KIND_PRODUCT  # type: ignore[attr-defined]


async def _do_reindex_store(store_id: int) -> None:
    async with async_session_factory() as session:
        doc = await build_store_document(session, store_id)
    client = get_meili_client()
    index = client.index("stores")
    if doc is None:
        try:
            task = await index.delete_document(store_id)
            await client.wait_for_task(task.task_uid)
        except Exception as exc:  # noqa: BLE001
            logger.debug("search.delete_store_skip store_id=%s err=%s", store_id, exc)
    else:
        task = await index.add_documents([doc], primary_key="id")
        await client.wait_for_task(task.task_uid)


@celery_app.task(
    base=_DLQTask,
    bind=True,
    name="search.reindex_store",
    autoretry_for=_REINDEX_AUTORETRY,
    retry_backoff=True,
    retry_backoff_max=_REINDEX_BACKOFF_MAX,
    max_retries=_REINDEX_MAX_RETRIES,
)
def reindex_store(self: Task, store_id: int) -> None:  # noqa: ARG001
    lock = _sync_redis.lock(
        f"meili_sync:store:{store_id}", timeout=5, blocking_timeout=1
    )
    if not lock.acquire(blocking=False):
        return
    try:
        _run_async(_do_reindex_store(store_id))
    finally:
        try:
            lock.release()
        except Exception:
            pass


reindex_store._dlq_kind = dlq.DEAD_LETTER_KIND_STORE  # type: ignore[attr-defined]


async def _do_reindex_products_for_store(store_id: int) -> list[int]:
    from app.models.store import StoreInventory

    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(StoreInventory.product_id)
                .where(StoreInventory.store_id == store_id)
                .distinct()
            )
        ).all()
    pids = [pid for (pid,) in rows]
    for pid in pids:
        reindex_master_product.delay(pid)
    return pids


@celery_app.task(name="search.reindex_products_for_store")
def reindex_products_for_store(store_id: int) -> None:
    _run_async(_do_reindex_products_for_store(store_id))


async def _do_reindex_products_by_category(category_id: int) -> list[int]:
    from app.models.catalog import Subcategory

    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(Subcategory.id).where(Subcategory.category_id == category_id)
            )
        ).all()
    sub_ids = [sid for (sid,) in rows]
    for sid in sub_ids:
        reindex_products_by_subcategory.delay(sid)
    return sub_ids


@celery_app.task(name="search.reindex_products_by_category")
def reindex_products_by_category(category_id: int) -> None:
    _run_async(_do_reindex_products_by_category(category_id))


async def _do_reindex_products_by_subcategory(subcategory_id: int) -> list[int]:
    from app.models.catalog import MasterProduct

    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(MasterProduct.id).where(MasterProduct.subcategory_id == subcategory_id)
            )
        ).all()
    pids = [pid for (pid,) in rows]
    for pid in pids:
        reindex_master_product.delay(pid)
    return pids


@celery_app.task(name="search.reindex_products_by_subcategory")
def reindex_products_by_subcategory(subcategory_id: int) -> None:
    _run_async(_do_reindex_products_by_subcategory(subcategory_id))


async def _do_rebuild_search_terms() -> None:
    from app.search.bootstrap import _to_settings_model
    from app.search.settings import INDEX_SETTINGS, SETTINGS_VERSION

    async with async_session_factory() as session:
        docs = await build_search_term_docs(session)
    client = get_meili_client()
    index = client.index("search_terms")
    update_task = await index.update_settings(
        _to_settings_model(INDEX_SETTINGS["search_terms"]())
    )
    await client.wait_for_task(update_task.task_uid)
    delete_task = await index.delete_all_documents()
    await client.wait_for_task(delete_task.task_uid)
    if docs:
        add_task = await index.add_documents(docs, primary_key="id")
        await client.wait_for_task(add_task.task_uid)
    marker_task = await index.add_documents(
        [{"id": f"_meta_v{SETTINGS_VERSION}", "_meta_version": SETTINGS_VERSION}],
        primary_key="id",
    )
    await client.wait_for_task(marker_task.task_uid)


@celery_app.task(name="search.rebuild_search_terms")
def rebuild_search_terms() -> None:
    _run_async(_do_rebuild_search_terms())


async def _do_prune_query_log() -> None:
    from sqlalchemy import text as sa_text

    async with async_session_factory() as session:
        await session.execute(
            sa_text(
                "DELETE FROM search_query_log WHERE created_at < NOW() - INTERVAL '90 days'"
            )
        )
        await session.commit()


@celery_app.task(name="search.prune_query_log")
def prune_query_log() -> None:
    _run_async(_do_prune_query_log())


async def _do_verify_drift(sample_size: int = 1000) -> int:
    """Sample N random products, diff DB vs Meili, re-enqueue divergent ones."""
    from sqlalchemy import func

    from app.models.catalog import MasterProduct
    from app.search.serialize import build_product_document

    client = get_meili_client()
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(MasterProduct.id)
                .order_by(func.random())
                .limit(sample_size)
            )
        ).all()
        ids = [pid for (pid,) in rows]

        index = client.index("products")
        divergent = 0
        for pid in ids:
            db_doc = await build_product_document(session, pid)
            try:
                meili_doc = await index.get_document(pid)
            except Exception:
                meili_doc = None
            if db_doc is None and meili_doc is None:
                continue
            if db_doc is None or meili_doc is None:
                divergent += 1
                reindex_master_product.delay(pid)
                continue
            # Compare a tight subset of fields — full equality fails on
            # updated_at (built fresh each time).
            keys = (
                "name_en", "brand", "is_active", "min_price",
                "in_stock_anywhere", "service_id", "category_id",
                "subcategory_id", "store_ids",
            )
            if any(db_doc.get(k) != meili_doc.get(k) for k in keys):
                divergent += 1
                reindex_master_product.delay(pid)
    return divergent


@celery_app.task(name="search.verify_drift")
def verify_drift() -> int:
    return _run_async(_do_verify_drift())


async def _do_reconcile(kind: str, force_deep: bool) -> None:
    from app.search.reconcile import reconcile_products, reconcile_stores

    async with async_session_factory() as session:
        client = get_meili_client()
        if kind == "product":
            await reconcile_products(session, client, force_deep=force_deep)
        elif kind == "store":
            await reconcile_stores(session, client, force_deep=force_deep)
        else:
            raise ValueError(f"unknown reconcile kind: {kind}")


@celery_app.task(name="search.reconcile_index")
def reconcile_index(kind: str, force_deep: bool = False) -> None:
    _run_async(_do_reconcile(kind, force_deep))


# ─── Schema-shape rebuild tasks ─────────────────────────────────────────────


async def _do_swap_products() -> int:
    from app.search.reindex import reindex_products_with_swap

    async with async_session_factory() as session:
        client = get_meili_client()
        return await reindex_products_with_swap(session, client)


@celery_app.task(name="search.swap_products")
def swap_products() -> None:
    lock = _sync_redis.lock(
        "meili:swap:in_progress:products", timeout=1800, blocking_timeout=1
    )
    if not lock.acquire(blocking=False):
        logger.info("search.swap_products.skipped already_running")
        return
    try:
        _run_async(_do_swap_products())
    finally:
        try:
            lock.release()
        except Exception:
            pass


async def _do_rebuild_stores() -> int:
    from app.search.bootstrap import _to_settings_model
    from app.search.reindex import reindex_stores as _reindex_stores
    from app.search.settings import INDEX_SETTINGS, SETTINGS_VERSION

    async with async_session_factory() as session:
        client = get_meili_client()
        # Push current settings so any sortable / filterable change ships
        # alongside the rebuild, then write the marker so the next boot's
        # ensure_indexes recognises this version as applied.
        index = client.index("stores")
        update_task = await index.update_settings(
            _to_settings_model(INDEX_SETTINGS["stores"]())
        )
        await client.wait_for_task(update_task.task_uid)
        n = await _reindex_stores(session, client)
        marker_task = await index.add_documents(
            [{"id": f"_meta_v{SETTINGS_VERSION}", "_meta_version": SETTINGS_VERSION}],
            primary_key="id",
        )
        await client.wait_for_task(marker_task.task_uid)
        return n


@celery_app.task(name="search.rebuild_stores")
def rebuild_stores() -> None:
    lock = _sync_redis.lock(
        "meili:swap:in_progress:stores", timeout=1800, blocking_timeout=1
    )
    if not lock.acquire(blocking=False):
        logger.info("search.rebuild_stores.skipped already_running")
        return
    try:
        _run_async(_do_rebuild_stores())
    finally:
        try:
            lock.release()
        except Exception:
            pass
