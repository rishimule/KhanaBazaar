# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from app.search import dlq
from app.search.reconcile import (
    STATE_KEY_TEMPLATE,
    _redis_client,
)


def _clear_cache_and_state() -> None:
    r = _redis_client()
    r.delete("search:health:cached")
    r.delete(STATE_KEY_TEMPLATE.format(kind="product"))
    r.delete(STATE_KEY_TEMPLATE.format(kind="store"))
    r.delete("search:dlq:product")
    r.delete("search:dlq:store")


@pytest.mark.asyncio
async def test_search_health_requires_admin(client: AsyncClient, meili_test_client) -> None:
    _clear_cache_and_state()
    res = await client.get("/api/v1/meta/search-health")
    # Without admin headers / dependency override, the route rejects.
    assert res.status_code in (401, 403)


@pytest.mark.asyncio
async def test_search_health_returns_expected_shape(
    client: AsyncClient, admin_auth_headers, meili_test_client
) -> None:
    _clear_cache_and_state()
    res = await client.get("/api/v1/meta/search-health", headers=admin_auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"products", "stores", "search_terms"}
    for k in ("products", "stores"):
        sub = body[k]
        assert "db_count" in sub
        assert "meili_count" in sub
        assert "dlq_size" in sub
        assert "lag_seconds" in sub
        assert "meili_unreachable" in sub
    assert "db_count" in body["search_terms"]


@pytest.mark.asyncio
async def test_search_health_reflects_dlq_size(
    client: AsyncClient, admin_auth_headers, meili_test_client
) -> None:
    _clear_cache_and_state()
    dlq.push("product", 1)
    dlq.push("product", 2)
    dlq.push("store", 99)

    res = await client.get("/api/v1/meta/search-health", headers=admin_auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["products"]["dlq_size"] == 2
    assert body["stores"]["dlq_size"] == 1


@pytest.mark.asyncio
async def test_search_health_surfaces_last_reconcile(
    client: AsyncClient, admin_auth_headers, meili_test_client
) -> None:
    _clear_cache_and_state()
    payload = {
        "kind": "product",
        "started_at": 1,
        "finished_at": 2,
        "mode": "deep",
        "shard": 3,
        "deltas": {"missing": [1, 2], "modified": [], "extra": []},
        "dlq_drained": 0,
        "error": None,
    }
    _redis_client().set(
        STATE_KEY_TEMPLATE.format(kind="product"), json.dumps(payload)
    )

    res = await client.get("/api/v1/meta/search-health", headers=admin_auth_headers)
    body = res.json()
    last = body["products"]["last_reconcile"]
    assert last is not None
    assert last["mode"] == "deep"
    assert last["deltas"] == {"missing": 2, "modified": 0, "extra": 0}


@pytest.mark.asyncio
async def test_search_health_cached_on_second_call(
    client: AsyncClient, admin_auth_headers, meili_test_client
) -> None:
    _clear_cache_and_state()
    res1 = await client.get("/api/v1/meta/search-health", headers=admin_auth_headers)
    assert res1.status_code == 200
    # Mutate DLQ; cached response should still show old value because the
    # 30s Redis cache absorbed the first body.
    dlq.push("product", 1234)
    res2 = await client.get("/api/v1/meta/search-health", headers=admin_auth_headers)
    assert res2.json()["products"]["dlq_size"] == res1.json()["products"]["dlq_size"]
