# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest

from app.search.serialize import build_store_document


@pytest.mark.asyncio
async def test_store_doc_carries_pause_fields(session, approved_seller_with_store):
    store = approved_seller_with_store.store
    store.is_paused = True
    session.add(store)
    await session.flush()
    doc = await build_store_document(session, store.id)
    assert doc is not None
    assert doc["is_paused"] is True
    assert "paused_until" in doc
    assert "paused_service_ids" in doc


@pytest.mark.asyncio
async def test_service_pause_enqueues_store_reindex(
    session, approved_seller_with_store, monkeypatch
):
    calls: list[int] = []
    from app.search import tasks as search_tasks

    monkeypatch.setattr(
        search_tasks.reindex_store_by_seller_profile,
        "delay",
        lambda spid: calls.append(spid),
    )
    svc_row = approved_seller_with_store.service_row
    svc_row.is_paused = True
    session.add(svc_row)
    await session.commit()
    assert approved_seller_with_store.profile.id in calls
