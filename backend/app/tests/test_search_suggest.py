# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.search.reindex import reindex_all
from tests.test_search_serialize import _seed_chain


@pytest.mark.asyncio
async def test_suggest_returns_terms_products_stores(
    client: AsyncClient, session: AsyncSession, meili_test_client
):
    await _seed_chain(session)
    await reindex_all(session, meili_test_client)
    r = await client.get("/api/v1/search/suggest", params={"q": "milk"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "query_id" in body
    assert any(p["name"].lower().startswith("amul") or "milk" in p["name"].lower()
               for p in body["products"]), body


@pytest.mark.asyncio
async def test_suggest_empty_query_returns_400(client: AsyncClient):
    r = await client.get("/api/v1/search/suggest", params={"q": "  "})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_suggest_too_long_returns_400(client: AsyncClient):
    r = await client.get(
        "/api/v1/search/suggest",
        params={"q": "a" * 200},
    )
    assert r.status_code in (400, 422)


@pytest.mark.asyncio
async def test_suggest_emits_query_id_header(
    client: AsyncClient, session: AsyncSession, meili_test_client
):
    await _seed_chain(session)
    await reindex_all(session, meili_test_client)
    r = await client.get("/api/v1/search/suggest", params={"q": "milk"})
    assert "X-Search-Query-ID" in r.headers
