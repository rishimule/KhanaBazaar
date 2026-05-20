# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


class _FakeStats:
    def __init__(self, n: int) -> None:
        self.number_of_documents = n


def _make_index(marker_present: bool, doc_count: int = 0) -> AsyncMock:
    idx = AsyncMock()
    if marker_present:
        idx.get_document = AsyncMock(return_value={"id": "marker"})
    else:
        idx.get_document = AsyncMock(side_effect=Exception("missing"))
    idx.get_stats = AsyncMock(return_value=_FakeStats(doc_count + 1))  # +1 marker
    idx.update_settings = AsyncMock(return_value=SimpleNamespace(task_uid="u"))
    idx.add_documents = AsyncMock(return_value=SimpleNamespace(task_uid="u2"))
    return idx


def _make_client(idx: AsyncMock) -> AsyncMock:
    client = AsyncMock()
    client.get_or_create_index = AsyncMock(return_value=idx)
    client.wait_for_task = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_bootstrap_skips_when_marker_at_current_version() -> None:
    from app.search.bootstrap import ensure_indexes

    idx = _make_index(marker_present=True)
    client = _make_client(idx)
    with patch(
        "app.search.bootstrap.INDEX_SETTINGS",
        {"products": lambda: {"searchableAttributes": ["name"]}},
    ):
        await ensure_indexes(client)
    idx.update_settings.assert_not_called()


@pytest.mark.asyncio
async def test_bootstrap_pushes_settings_inline_when_index_empty() -> None:
    from app.search.bootstrap import ensure_indexes

    idx = _make_index(marker_present=False, doc_count=0)
    client = _make_client(idx)
    with patch(
        "app.search.bootstrap.INDEX_SETTINGS",
        {"products": lambda: {"searchableAttributes": ["name"]}},
    ):
        await ensure_indexes(client)

    idx.update_settings.assert_called_once()
    idx.add_documents.assert_called_once()


@pytest.mark.asyncio
async def test_bootstrap_handoff_to_swap_when_marker_stale_and_docs_present() -> None:
    from app.search.bootstrap import ensure_indexes

    idx = _make_index(marker_present=False, doc_count=50)
    client = _make_client(idx)
    with patch(
        "app.search.bootstrap.INDEX_SETTINGS",
        {"products": lambda: {"searchableAttributes": ["name"]}},
    ), patch("app.search.tasks.swap_products.delay") as swap_delay:
        await ensure_indexes(client)

    swap_delay.assert_called_once()
    idx.update_settings.assert_not_called()
    idx.add_documents.assert_not_called()


@pytest.mark.asyncio
async def test_bootstrap_handoff_for_stores_uses_rebuild_stores() -> None:
    from app.search.bootstrap import ensure_indexes

    idx = _make_index(marker_present=False, doc_count=10)
    client = _make_client(idx)
    with patch(
        "app.search.bootstrap.INDEX_SETTINGS",
        {"stores": lambda: {"searchableAttributes": ["name"]}},
    ), patch("app.search.tasks.rebuild_stores.delay") as rebuild_delay:
        await ensure_indexes(client)

    rebuild_delay.assert_called_once()
    idx.update_settings.assert_not_called()


@pytest.mark.asyncio
async def test_bootstrap_handoff_for_search_terms_uses_rebuild_terms() -> None:
    from app.search.bootstrap import ensure_indexes

    idx = _make_index(marker_present=False, doc_count=999)
    client = _make_client(idx)
    with patch(
        "app.search.bootstrap.INDEX_SETTINGS",
        {"search_terms": lambda: {"searchableAttributes": ["term"]}},
    ), patch("app.search.tasks.rebuild_search_terms.delay") as terms_delay:
        await ensure_indexes(client)

    terms_delay.assert_called_once()
    idx.update_settings.assert_not_called()
