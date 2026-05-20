# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Bulk reindex CLI: `python -m app.search.reindex --all` (etc.)."""
from __future__ import annotations

import argparse
import asyncio
import logging
import time
from typing import Optional

from meilisearch_python_sdk import AsyncClient
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.session import async_session_factory
from app.models.catalog import MasterProduct
from app.models.store import Store
from app.search.bootstrap import _to_settings_model, ensure_indexes
from app.search.client import get_meili_client
from app.search.serialize import (
    build_product_document,
    build_search_term_docs,
    build_store_document,
)
from app.search.settings import INDEX_SETTINGS, SETTINGS_VERSION

logger = logging.getLogger(__name__)
BATCH = 500


async def reindex_products(
    session: AsyncSession, client: AsyncClient, since_ts: Optional[float] = None
) -> int:
    q = select(MasterProduct.id).order_by(MasterProduct.id)
    if since_ts is not None:
        from datetime import datetime, timezone
        cutoff = datetime.fromtimestamp(since_ts, tz=timezone.utc)
        q = q.where(MasterProduct.updated_at >= cutoff)
    ids = [pid for (pid,) in (await session.execute(q)).all()]
    index = client.index("products")
    pushed = 0
    for i in range(0, len(ids), BATCH):
        batch_ids = ids[i : i + BATCH]
        docs = []
        for pid in batch_ids:
            doc = await build_product_document(session, pid)
            if doc is not None:
                docs.append(doc)
        if docs:
            task = await index.add_documents(docs, primary_key="id")
            await client.wait_for_task(task.task_uid)
        pushed += len(docs)
        logger.info("reindex.products.batch pushed=%d total=%d", len(docs), pushed)
    return pushed


async def reindex_stores(session: AsyncSession, client: AsyncClient) -> int:
    ids = [sid for (sid,) in (await session.execute(select(Store.id))).all()]
    index = client.index("stores")
    docs = []
    for sid in ids:
        d = await build_store_document(session, sid)
        if d is not None:
            docs.append(d)
    if docs:
        task = await index.add_documents(docs, primary_key="id")
        await client.wait_for_task(task.task_uid)
    return len(docs)


async def reindex_search_terms(
    session: AsyncSession, client: AsyncClient
) -> int:
    docs = await build_search_term_docs(session)
    index = client.index("search_terms")
    delete_task = await index.delete_all_documents()
    await client.wait_for_task(delete_task.task_uid)
    if docs:
        add_task = await index.add_documents(docs, primary_key="id")
        await client.wait_for_task(add_task.task_uid)
    return len(docs)


async def reindex_all(
    session: AsyncSession, client: AsyncClient
) -> dict[str, int]:
    await ensure_indexes(client)
    return {
        "products": await reindex_products(session, client),
        "stores": await reindex_stores(session, client),
        "search_terms": await reindex_search_terms(session, client),
    }


async def reindex_products_with_swap(
    session: AsyncSession, client: AsyncClient
) -> int:
    """Build into products_vNext, swap with current alias, drop the old index.

    Also writes the `_meta_v{SETTINGS_VERSION}` marker into the new index
    so the next `ensure_indexes` boot recognises the schema is current
    and does NOT trigger another swap.
    """
    start_ts = time.time()
    next_uid = f"products_v{SETTINGS_VERSION}_{int(start_ts)}"
    # SDK v7 returns the AsyncIndex directly (waits internally).
    next_index = await client.create_index(next_uid, primary_key="id")
    update_task = await next_index.update_settings(
        _to_settings_model(INDEX_SETTINGS["products"]())
    )
    await client.wait_for_task(update_task.task_uid)

    marker_task = await next_index.add_documents(
        [{"id": f"_meta_v{SETTINGS_VERSION}", "_meta_version": SETTINGS_VERSION}],
        primary_key="id",
    )
    await client.wait_for_task(marker_task.task_uid)

    ids = [pid for (pid,) in (await session.execute(select(MasterProduct.id))).all()]
    for i in range(0, len(ids), BATCH):
        docs = [
            d
            for d in [
                await build_product_document(session, pid)
                for pid in ids[i : i + BATCH]
            ]
            if d is not None
        ]
        if docs:
            task = await next_index.add_documents(docs, primary_key="id")
            await client.wait_for_task(task.task_uid)

    swap = await client.swap_indexes([(next_uid, "products")])
    await client.wait_for_task(swap.task_uid)
    drop = await client.index(next_uid).delete()
    await client.wait_for_task(drop.task_uid)
    return len(ids)


def _parse_since(spec: Optional[str]) -> Optional[float]:
    if spec is None:
        return None
    unit = spec[-1]
    n = int(spec[:-1])
    seconds = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    return time.time() - n * seconds


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="app.search.reindex")
    p.add_argument("--all", action="store_true")
    p.add_argument("--products", action="store_true")
    p.add_argument("--stores", action="store_true")
    p.add_argument("--search-terms", action="store_true")
    p.add_argument("--swap-on-finish", action="store_true")
    p.add_argument("--since", default=None, help="e.g. 1h, 24h, 30m")
    return p


async def _main(argv: Optional[list[str]] = None) -> None:
    args = _build_parser().parse_args(argv)
    since_ts = _parse_since(args.since)
    client = get_meili_client()
    async with async_session_factory() as session:
        if args.all:
            print(await reindex_all(session, client))
            return
        if args.products:
            if args.swap_on_finish:
                n = await reindex_products_with_swap(session, client)
            else:
                n = await reindex_products(session, client, since_ts)
            print({"products": n})
        if args.stores:
            print({"stores": await reindex_stores(session, client)})
        if args.search_terms:
            print({"search_terms": await reindex_search_terms(session, client)})


if __name__ == "__main__":
    asyncio.run(_main())
