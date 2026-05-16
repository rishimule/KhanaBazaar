# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest


@pytest.mark.asyncio
async def test_meili_client_health(meili_test_client):
    health = await meili_test_client.health()
    assert health.status == "available"


@pytest.mark.asyncio
async def test_meili_test_client_has_three_indexes(meili_test_client):
    indexes = await meili_test_client.get_indexes()
    uids = {idx.uid for idx in indexes}
    assert {"products", "stores", "search_terms"}.issubset(uids)
