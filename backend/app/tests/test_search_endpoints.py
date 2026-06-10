# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.search.reindex import reindex_all
from tests.test_search_serialize import _seed_chain


@pytest.mark.asyncio
async def test_products_basic(
    client: AsyncClient, session: AsyncSession, meili_test_client
):
    await _seed_chain(session)
    await reindex_all(session, meili_test_client)
    r = await client.get("/api/v1/search/products", params={"q": "milk"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1
    assert body["sort"] == "relevance"
    assert "facets" in body


@pytest.mark.asyncio
async def test_products_invalid_sort_400(
    client: AsyncClient, session: AsyncSession, meili_test_client
):
    await _seed_chain(session)
    await reindex_all(session, meili_test_client)
    r = await client.get("/api/v1/search/products", params={"q": "milk", "sort": "foo"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_products_store_scope_passes_through(
    client: AsyncClient, session: AsyncSession, meili_test_client
):
    ids = await _seed_chain(session)
    await reindex_all(session, meili_test_client)
    r = await client.get(
        "/api/v1/search/products",
        params={"q": "milk", "store_id": ids["store_id"]},
    )
    body = r.json()
    for p in body["products"]:
        assert any(o["store_id"] == ids["store_id"] for o in p["per_store_offers"])


@pytest.mark.asyncio
async def test_compare_returns_offers(
    client: AsyncClient, session: AsyncSession
):
    ids = await _seed_chain(session)
    r = await client.get(f"/api/v1/search/products/{ids['product_id']}/stores")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["offers"]) == 1
    assert body["offers"][0]["price"] == 68.0


@pytest.mark.asyncio
async def test_compare_404(client: AsyncClient):
    r = await client.get("/api/v1/search/products/99999/stores")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_compare_includes_product_images(
    client: AsyncClient, session: AsyncSession
):
    from app.models.catalog import MasterProductImage

    ids = await _seed_chain(session)
    session.add(
        MasterProductImage(
            master_product_id=ids["product_id"], position=0,
            url="https://x.test/a.jpg", source="external",
        )
    )
    session.add(
        MasterProductImage(
            master_product_id=ids["product_id"], position=1,
            url="https://x.test/b.jpg", source="external",
        )
    )
    await session.commit()

    r = await client.get(f"/api/v1/search/products/{ids['product_id']}/stores")
    assert r.status_code == 200, r.text
    imgs = r.json()["product"]["images"]
    assert [i["url"] for i in imgs] == ["https://x.test/a.jpg", "https://x.test/b.jpg"]
    assert imgs[0]["position"] == 0


@pytest.mark.asyncio
async def test_stores_endpoint(
    client: AsyncClient, session: AsyncSession, meili_test_client
):
    await _seed_chain(session)
    await reindex_all(session, meili_test_client)
    r = await client.get("/api/v1/search/stores", params={"q": "kirana"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1


@pytest.mark.asyncio
async def test_click_endpoint(
    client: AsyncClient, session: AsyncSession, meili_test_client
):
    await _seed_chain(session)
    await reindex_all(session, meili_test_client)
    r = await client.get("/api/v1/search/suggest", params={"q": "milk"})
    qid = r.headers["X-Search-Query-ID"]
    r2 = await client.post(
        "/api/v1/search/click",
        json={"query_id": qid, "clicked_product_id": 1, "position": 0},
    )
    assert r2.status_code == 204


@pytest.mark.asyncio
async def test_click_unknown_query_id_204(client: AsyncClient):
    import uuid as _uuid

    r = await client.post(
        "/api/v1/search/click",
        json={"query_id": str(_uuid.uuid4()), "position": 0},
    )
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_products_subcategory_filter(
    client: AsyncClient, session: AsyncSession, meili_test_client
):
    ids = await _seed_chain(session)
    await reindex_all(session, meili_test_client)
    r = await client.get(
        "/api/v1/search/products",
        params={"q": "", "subcategory_id": ids["subcategory_id"]},
    )
    assert r.status_code == 200, r.text
    assert any(p["id"] == ids["product_id"] for p in r.json()["products"])
    r2 = await client.get(
        "/api/v1/search/products", params={"q": "", "subcategory_id": 999999}
    )
    assert r2.json()["total"] == 0
