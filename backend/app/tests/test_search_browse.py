# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.search.reindex import reindex_all
from tests.test_search_serialize import _seed_chain


@pytest.mark.asyncio
async def test_browse_groups_by_category(
    client: AsyncClient, session: AsyncSession, meili_test_client
):
    ids = await _seed_chain(session)
    await reindex_all(session, meili_test_client)
    r = await client.get(
        "/api/v1/search/browse", params={"service_id": ids["service_id"]}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["service_id"] == ids["service_id"]
    assert body["service_name"] == "Grocery"
    # One seeded category ("Dairy") with the one product
    assert len(body["categories"]) == 1
    cat = body["categories"][0]
    assert cat["name"] == "Dairy"
    assert len(cat["products"]) == 1
    prod = cat["products"][0]
    assert prod["id"] == ids["product_id"]
    assert prod["name"] == "Amul Gold Milk"
    assert prod["min_price"] == 68.0
    # Lean card: no per-store offers leaked into the browse payload
    assert "per_store_offers" not in prod
