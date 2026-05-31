# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest

from app.models.profile import SellerProfileService
from app.services.store_pause import set_service_pause, set_store_pause


@pytest.mark.asyncio
async def test_set_store_pause_sets_and_clears(session, approved_seller_with_store):
    store = approved_seller_with_store.store

    await set_store_pause(session, store, is_paused=True, reason="Diwali", paused_until=None)
    assert store.is_paused is True
    assert store.pause_reason == "Diwali"

    await set_store_pause(session, store, is_paused=False, reason=None, paused_until=None)
    assert store.is_paused is False
    assert store.pause_reason is None
    assert store.paused_until is None


@pytest.mark.asyncio
async def test_set_service_pause_toggles_row(session, approved_seller_with_store):
    profile = approved_seller_with_store.profile
    service_id = approved_seller_with_store.service_id

    row = await set_service_pause(
        session, seller_profile_id=profile.id, service_id=service_id,
        is_paused=True, reason="No pharmacist", paused_until=None,
    )
    assert isinstance(row, SellerProfileService)
    assert row.is_paused is True

    row = await set_service_pause(
        session, seller_profile_id=profile.id, service_id=service_id,
        is_paused=False, reason=None, paused_until=None,
    )
    assert row.is_paused is False
    assert row.pause_reason is None
