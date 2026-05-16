# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Push index settings on app startup if version differs."""
from __future__ import annotations

import logging

from meilisearch_python_sdk import AsyncClient
from meilisearch_python_sdk.models.settings import (
    MeilisearchSettings,
    MinWordSizeForTypos,
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
    return MeilisearchSettings(
        searchableAttributes=raw.get("searchableAttributes"),
        filterableAttributes=raw.get("filterableAttributes"),
        sortableAttributes=raw.get("sortableAttributes"),
        rankingRules=raw.get("rankingRules"),
        typoTolerance=typo_model,
        synonyms=raw.get("synonyms"),
        stopWords=raw.get("stopWords"),
    )

logger = logging.getLogger(__name__)

_META_ID_PREFIX = "_meta_v"


async def ensure_indexes(client: AsyncClient) -> None:
    """Create each index if missing; push settings if version metadata is absent."""
    for uid, settings_fn in INDEX_SETTINGS.items():
        # get_or_create_index handles both fresh and existing indexes cleanly.
        index = await client.get_or_create_index(uid, primary_key="id")

        marker_id = f"{_META_ID_PREFIX}{SETTINGS_VERSION}"
        try:
            await index.get_document(marker_id)
            logger.debug("search.bootstrap.skip uid=%s version=%s", uid, SETTINGS_VERSION)
            continue
        except Exception:
            # Document not found — either fresh index or older settings version.
            pass

        update_task = await index.update_settings(_to_settings_model(settings_fn()))
        await client.wait_for_task(update_task.task_uid)
        add_task = await index.add_documents(
            [{"id": marker_id, "_meta_version": SETTINGS_VERSION}],
            primary_key="id",
        )
        await client.wait_for_task(add_task.task_uid)
        logger.info("search.bootstrap.applied uid=%s version=%s", uid, SETTINGS_VERSION)
