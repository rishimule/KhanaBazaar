# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""When a location is set but no store delivers there, /products and /suggest
must return zero products (mirroring /browse's empty-categories behaviour).
The seeded store sits at lat 19.07, lng 72.87 with a 5 km radius."""
import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.search.reindex import reindex_all
from tests.test_search_serialize import _seed_chain

IN_AREA = {"lat": 19.07, "lng": 72.87}
OUT_OF_AREA = {"lat": 28.6, "lng": 77.2}  # Delhi-ish, far outside the radius


@pytest.mark.asyncio
async def test_products_returns_results_in_area(
    client: AsyncClient, session: AsyncSession, meili_test_client
):
    await _seed_chain(session)
    await reindex_all(session, meili_test_client)
    r = await client.get(
        "/api/v1/search/products", params={"q": "milk", **IN_AREA}
    )
    assert r.status_code == 200, r.text
    assert r.json()["total"] >= 1  # sanity: the query itself matches in-area


@pytest.mark.asyncio
async def test_products_empty_when_no_store_serviceable(
    client: AsyncClient, session: AsyncSession, meili_test_client
):
    await _seed_chain(session)
    await reindex_all(session, meili_test_client)
    r = await client.get(
        "/api/v1/search/products", params={"q": "milk", **OUT_OF_AREA}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["products"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_suggest_empty_when_no_store_serviceable(
    client: AsyncClient, session: AsyncSession, meili_test_client
):
    await _seed_chain(session)
    await reindex_all(session, meili_test_client)
    r = await client.get(
        "/api/v1/search/suggest", params={"q": "milk", **OUT_OF_AREA}
    )
    assert r.status_code == 200, r.text
    assert r.json()["products"] == []
