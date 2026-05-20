# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Push index settings on app startup if version differs."""
from __future__ import annotations

import logging

from meilisearch_python_sdk import AsyncClient
from meilisearch_python_sdk.models.settings import (
    MeilisearchSettings,
    MinWordSizeForTypos,
    Pagination,
    TypoTolerance,
)

from app.search.settings import INDEX_SETTINGS, SETTINGS_VERSION


def _to_settings_model(raw: dict) -> MeilisearchSettings:
    """Convert a plain settings dict into the SDK's pydantic settings model."""
    typo = raw.get("typoTolerance")
    typo_model = None
    if typo is not None:
        mw = typo.get("minWordSizeForTypos") or {}
        typo_model = TypoTolerance(
            minWordSizeForTypos=MinWordSizeForTypos(
                oneTypo=mw.get("oneTypo"),
                twoTypos=mw.get("twoTypos"),
            ) if mw else None,
        )
    pag = raw.get("pagination")
    pag_model = Pagination(maxTotalHits=pag["maxTotalHits"]) if pag else None
    return MeilisearchSettings(
        searchableAttributes=raw.get("searchableAttributes"),
        filterableAttributes=raw.get("filterableAttributes"),
        sortableAttributes=raw.get("sortableAttributes"),
        rankingRules=raw.get("rankingRules"),
        typoTolerance=typo_model,
        synonyms=raw.get("synonyms"),
        stopWords=raw.get("stopWords"),
        pagination=pag_model,
    )

logger = logging.getLogger(__name__)

_META_ID_PREFIX = "_meta_v"


async def ensure_indexes(client: AsyncClient) -> None:
    """Create each index if missing; push settings on first boot or
    hand off to a Celery rebuild task on a settings-version bump.

    Three paths per index:
        1. Marker present at current version → no-op.
        2. Marker absent AND index has no documents → push settings + write
           marker inline (fresh boot path; cheap).
        3. Marker absent AND index has documents → schema-shape change.
           Enqueue a Celery rebuild task; do NOT push settings in-place
           because the running index may still serve queries against the
           old schema while the swap builds the new one.
    """
    for uid, settings_fn in INDEX_SETTINGS.items():
        index = await client.get_or_create_index(uid, primary_key="id")

        marker_id = f"{_META_ID_PREFIX}{SETTINGS_VERSION}"
        try:
            await index.get_document(marker_id)
            logger.debug("search.bootstrap.skip uid=%s version=%s", uid, SETTINGS_VERSION)
            continue
        except Exception:
            pass

        try:
            stats = await index.get_stats()
            doc_count = max(stats.number_of_documents - 1, 0)
        except Exception:
            doc_count = 0

        if doc_count == 0:
            update_task = await index.update_settings(_to_settings_model(settings_fn()))
            await client.wait_for_task(update_task.task_uid)
            add_task = await index.add_documents(
                [{"id": marker_id, "_meta_version": SETTINGS_VERSION}],
                primary_key="id",
            )
            await client.wait_for_task(add_task.task_uid)
            logger.info(
                "search.bootstrap.applied uid=%s version=%s", uid, SETTINGS_VERSION
            )
            continue

        # Late import — tasks.py imports search.client which imports settings;
        # bootstrap.py is imported from app.__init__ at startup, so the
        # top-level import would race with the celery_app initialisation.
        from app.search.tasks import (
            rebuild_search_terms,
            rebuild_stores,
            swap_products,
        )

        if uid == "products":
            swap_products.delay()
        elif uid == "stores":
            rebuild_stores.delay()
        elif uid == "search_terms":
            rebuild_search_terms.delay()
        logger.info(
            "search.bootstrap.handoff uid=%s version=%s docs=%s",
            uid, SETTINGS_VERSION, doc_count,
        )
