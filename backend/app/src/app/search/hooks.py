# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""SQLAlchemy after_insert/after_update/after_delete listeners that enqueue
Meilisearch sync tasks.

Listeners run synchronously inside the SQLAlchemy mapper flush so they can
only call sync code. They call Celery `.delay(...)` (sync) which queues the
async sync work to a worker process.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import event

from app.models.catalog import (
    CategoryTranslation,
    MasterProduct,
    MasterProductTranslation,
    SubcategoryTranslation,
)
from app.models.store import Store, StoreInventory
from app.search.tasks import (
    reindex_master_product,
    reindex_products_by_subcategory,
    reindex_products_for_store,
    reindex_store,
)

logger = logging.getLogger(__name__)
_registered = False


def _on_master_product_change(mapper: Any, connection: Any, target: MasterProduct) -> None:
    reindex_master_product.delay(target.id)


def _on_translation_change(
    mapper: Any, connection: Any, target: MasterProductTranslation
) -> None:
    reindex_master_product.delay(target.master_product_id)


def _on_inventory_change(mapper: Any, connection: Any, target: StoreInventory) -> None:
    reindex_master_product.delay(target.product_id)


def _on_store_change(mapper: Any, connection: Any, target: Store) -> None:
    reindex_store.delay(target.id)
    reindex_products_for_store.delay(target.id)


def _on_subcategory_translation(
    mapper: Any, connection: Any, target: SubcategoryTranslation
) -> None:
    reindex_products_by_subcategory.delay(target.subcategory_id)


def _on_category_translation(
    mapper: Any, connection: Any, target: CategoryTranslation
) -> None:
    # Fan out: every subcategory under this category gets re-enqueued.
    # Listeners can't run async work, so enqueue a single bulk task that
    # discovers subcategories from inside the worker.
    from app.search.tasks import reindex_products_by_category

    reindex_products_by_category.delay(target.category_id)


def register_search_hooks() -> None:
    """Idempotently attach SQLAlchemy listeners for search sync."""
    global _registered
    if _registered:
        return
    _registered = True

    event.listen(MasterProduct, "after_insert", _on_master_product_change)
    event.listen(MasterProduct, "after_update", _on_master_product_change)
    event.listen(MasterProduct, "after_delete", _on_master_product_change)

    event.listen(MasterProductTranslation, "after_insert", _on_translation_change)
    event.listen(MasterProductTranslation, "after_update", _on_translation_change)

    event.listen(StoreInventory, "after_insert", _on_inventory_change)
    event.listen(StoreInventory, "after_update", _on_inventory_change)
    event.listen(StoreInventory, "after_delete", _on_inventory_change)

    event.listen(Store, "after_insert", _on_store_change)
    event.listen(Store, "after_update", _on_store_change)
    event.listen(Store, "after_delete", _on_store_change)

    event.listen(SubcategoryTranslation, "after_insert", _on_subcategory_translation)
    event.listen(SubcategoryTranslation, "after_update", _on_subcategory_translation)

    event.listen(CategoryTranslation, "after_insert", _on_category_translation)
    event.listen(CategoryTranslation, "after_update", _on_category_translation)

    logger.info("search.hooks.registered")
