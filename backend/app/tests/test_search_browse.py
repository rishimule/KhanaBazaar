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


@pytest.mark.asyncio
async def test_browse_includes_subcategories(
    client: AsyncClient, session: AsyncSession, meili_test_client
):
    ids = await _seed_chain(session)
    await reindex_all(session, meili_test_client)
    r = await client.get(
        "/api/v1/search/browse", params={"service_id": ids["service_id"]}
    )
    assert r.status_code == 200, r.text
    cat = r.json()["categories"][0]
    assert "subcategories" in cat
    subs = cat["subcategories"]
    # Only subcategories with in-area products appear; seeded "Milk" must.
    assert any(
        s["id"] == ids["subcategory_id"] and s["name"] == "Milk" for s in subs
    )


@pytest.mark.asyncio
async def test_browse_serviceable_filter_in_area(
    client: AsyncClient, session: AsyncSession, meili_test_client
):
    ids = await _seed_chain(session)
    await reindex_all(session, meili_test_client)
    # Store seeded at lat 19.07, lng 72.87, radius 5 km → query nearby
    r = await client.get(
        "/api/v1/search/browse",
        params={"service_id": ids["service_id"], "lat": 19.07, "lng": 72.87},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["categories"]) == 1


@pytest.mark.asyncio
async def test_browse_serviceable_filter_out_of_area(
    client: AsyncClient, session: AsyncSession, meili_test_client
):
    ids = await _seed_chain(session)
    await reindex_all(session, meili_test_client)
    # Far away (Delhi-ish) → no serviceable store → empty categories
    r = await client.get(
        "/api/v1/search/browse",
        params={"service_id": ids["service_id"], "lat": 28.61, "lng": 77.20},
    )
    assert r.status_code == 200, r.text
    assert r.json()["categories"] == []


@pytest.mark.asyncio
async def test_browse_no_location_returns_all(
    client: AsyncClient, session: AsyncSession, meili_test_client
):
    ids = await _seed_chain(session)
    await reindex_all(session, meili_test_client)
    r = await client.get(
        "/api/v1/search/browse", params={"service_id": ids["service_id"]}
    )
    assert len(r.json()["categories"]) == 1


@pytest.mark.asyncio
async def test_browse_unknown_service_404(
    client: AsyncClient, session: AsyncSession, meili_test_client
):
    await _seed_chain(session)
    await reindex_all(session, meili_test_client)
    r = await client.get("/api/v1/search/browse", params={"service_id": 999999})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_browse_locale_hindi(
    client: AsyncClient, session: AsyncSession, meili_test_client
):
    ids = await _seed_chain(session)
    await reindex_all(session, meili_test_client)
    r = await client.get(
        "/api/v1/search/browse",
        params={"service_id": ids["service_id"]},
        headers={"Accept-Language": "hi"},
    )
    body = r.json()
    assert body["categories"][0]["products"][0]["name"] == "अमूल गोल्ड दूध"
