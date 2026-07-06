# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""SQLAlchemy after_commit listeners that enqueue Meilisearch sync tasks.

Mapper-level `after_insert/update/delete` events fire mid-flush, *before* the
transaction commits — so if the surrounding transaction rolls back, work is
still enqueued. Instead, we attach `after_flush` to the session to collect
target IDs, then `after_commit` to flush the enqueue list. On rollback we
discard the collected IDs.

Listeners run synchronously inside SQLAlchemy event hooks so they can only
call sync code; they enqueue Celery `.delay(...)` calls (sync) which run on
a worker process.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session as SyncSession

from app.models.catalog import (
    CategoryTranslation,
    MasterProduct,
    MasterProductTranslation,
    SubcategoryTranslation,
)
from app.models.platform_fee import FeeArrangement
from app.models.profile import SellerProfileService
from app.models.store import Store, StoreInventory

logger = logging.getLogger(__name__)
_registered = False

# Per-session pending enqueues keyed by session id. Each value is a dict of
# action-name → set of ids to enqueue once the surrounding txn commits.
_PENDING_ATTR = "_search_pending_enqueues"


def _pending(session: SyncSession) -> dict[str, set[int]]:
    bag = getattr(session, _PENDING_ATTR, None)
    if bag is None:
        bag = {
            "product": set(),
            "store": set(),
            "products_for_store": set(),
            "subcategory": set(),
            "category": set(),
            "seller_service_profile": set(),
        }
        setattr(session, _PENDING_ATTR, bag)
    return bag


def _drain_pending(session: SyncSession) -> None:
    bag = getattr(session, _PENDING_ATTR, None)
    if bag is not None:
        setattr(session, _PENDING_ATTR, None)


def _after_flush(session: SyncSession, flush_context: Any) -> None:
    """Collect target IDs for every dirty/new/deleted instance of interest."""
    bag = _pending(session)
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        if isinstance(obj, MasterProduct):
            bag["product"].add(obj.id)
        elif isinstance(obj, MasterProductTranslation):
            bag["product"].add(obj.master_product_id)
        elif isinstance(obj, StoreInventory):
            bag["product"].add(obj.product_id)
        elif isinstance(obj, Store):
            bag["store"].add(obj.id)
            bag["products_for_store"].add(obj.id)
        elif isinstance(obj, FeeArrangement):
            bag["store"].add(obj.store_id)
            bag["products_for_store"].add(obj.store_id)
        elif isinstance(obj, SubcategoryTranslation):
            bag["subcategory"].add(obj.subcategory_id)
        elif isinstance(obj, CategoryTranslation):
            bag["category"].add(obj.category_id)
        elif isinstance(obj, SellerProfileService):
            bag["seller_service_profile"].add(obj.seller_profile_id)


def _after_commit(session: SyncSession) -> None:
    """Fire Celery enqueues for everything observed since the last commit."""
    bag = getattr(session, _PENDING_ATTR, None)
    if bag is None:
        return
    # Late imports — task module imports config, which imports settings; keep
    # the listener module side-effect-free at import time.
    from app.search.tasks import (
        reindex_master_product,
        reindex_products_by_category,
        reindex_products_by_subcategory,
        reindex_products_for_store,
        reindex_store,
        reindex_store_by_seller_profile,
    )
    for pid in bag["product"]:
        reindex_master_product.delay(pid)
    for sid in bag["store"]:
        reindex_store.delay(sid)
    for sid in bag["products_for_store"]:
        reindex_products_for_store.delay(sid)
    for sid in bag["subcategory"]:
        reindex_products_by_subcategory.delay(sid)
    for cid in bag["category"]:
        reindex_products_by_category.delay(cid)
    for spid in bag["seller_service_profile"]:
        reindex_store_by_seller_profile.delay(spid)
    _drain_pending(session)


def _after_rollback(session: SyncSession) -> None:
    _drain_pending(session)


def register_search_hooks() -> None:
    """Idempotently attach SQLAlchemy session-level listeners for search sync."""
    global _registered
    if _registered:
        return
    _registered = True

    # Session listeners — fire across all sync sessions including the sync
    # session SQLAlchemy creates behind asyncpg's AsyncSession.
    event.listen(SyncSession, "after_flush", _after_flush)
    event.listen(SyncSession, "after_commit", _after_commit)
    event.listen(SyncSession, "after_rollback", _after_rollback)

    logger.info("search.hooks.registered")
