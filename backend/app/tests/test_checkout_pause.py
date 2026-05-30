# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from fastapi import HTTPException

from app.services.checkout import (
    _validate_service_active_for_store,
    _validate_stores_active,
)


@pytest.mark.asyncio
async def test_validate_stores_active_rejects_paused(session, approved_seller_with_store):
    store = approved_seller_with_store.store
    store.is_paused = True
    session.add(store)
    await session.flush()
    with pytest.raises(HTTPException) as exc:
        await _validate_stores_active(session, [store.id])
    assert exc.value.detail["detail"] == "store_paused"


@pytest.mark.asyncio
async def test_validate_service_rejects_paused(session, approved_seller_with_store):
    store = approved_seller_with_store.store
    service_id = approved_seller_with_store.service_id
    svc_row = approved_seller_with_store.service_row
    svc_row.is_paused = True
    session.add(svc_row)
    await session.flush()
    with pytest.raises(HTTPException) as exc:
        await _validate_service_active_for_store(session, store.id, service_id)
    assert exc.value.detail["detail"] == "service_paused"


@pytest.mark.asyncio
async def test_validate_service_active_unpaused_passes(session, approved_seller_with_store):
    store = approved_seller_with_store.store
    service_id = approved_seller_with_store.service_id
    # No pause set — an unpaused, offered, active service must NOT raise.
    await _validate_service_active_for_store(session, store.id, service_id)
