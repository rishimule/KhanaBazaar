# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Admin categories CRUD: create, list with service filter, move category
between services, slug-clash detection on move, soft delete cascade to
public reads."""

import pytest
from httpx import AsyncClient

from tests.conftest import _Stub


@pytest.mark.asyncio
async def test_create_category(
    client: AsyncClient, admin_auth_headers: dict[str, str], seeded_service: _Stub
) -> None:
    r = await client.post(
        "/api/v1/catalog/admin/categories",
        headers=admin_auth_headers,
        json={"service_id": seeded_service.id, "name": "Produce", "sort_order": 1},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["service_id"] == seeded_service.id
    assert body["slug"] == "produce"
    assert body["is_active"] is True


@pytest.mark.asyncio
async def test_list_categories_filter_by_service(
    client: AsyncClient, admin_auth_headers: dict[str, str], seeded_service: _Stub
) -> None:
    await client.post(
        "/api/v1/catalog/admin/categories",
        headers=admin_auth_headers,
        json={"service_id": seeded_service.id, "name": "Snacks"},
    )
    r = await client.get(
        f"/api/v1/catalog/admin/categories?service_id={seeded_service.id}",
        headers=admin_auth_headers,
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert items
    assert all(c["service_id"] == seeded_service.id for c in items)


@pytest.mark.asyncio
async def test_move_category_to_different_service(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_service: _Stub,
) -> None:
    other = (await client.post(
        "/api/v1/catalog/admin/services",
        headers=admin_auth_headers,
        json={"name": "OtherSvc"},
    )).json()
    cat = (await client.post(
        "/api/v1/catalog/admin/categories",
        headers=admin_auth_headers,
        json={"service_id": seeded_service.id, "name": "Dairy"},
    )).json()
    r = await client.put(
        f"/api/v1/catalog/admin/categories/{cat['id']}",
        headers=admin_auth_headers,
        json={"service_id": other["id"]},
    )
    assert r.status_code == 200
    assert r.json()["service_id"] == other["id"]


@pytest.mark.asyncio
async def test_move_category_slug_clash_409(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_service: _Stub,
) -> None:
    other = (await client.post(
        "/api/v1/catalog/admin/services",
        headers=admin_auth_headers,
        json={"name": "OtherSvc2"},
    )).json()
    await client.post(
        "/api/v1/catalog/admin/categories",
        headers=admin_auth_headers,
        json={"service_id": seeded_service.id, "name": "Bread"},
    )
    target = (await client.post(
        "/api/v1/catalog/admin/categories",
        headers=admin_auth_headers,
        json={"service_id": other["id"], "name": "Bread"},
    )).json()
    r = await client.put(
        f"/api/v1/catalog/admin/categories/{target['id']}",
        headers=admin_auth_headers,
        json={"service_id": seeded_service.id},
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "slug_exists_in_destination"


@pytest.mark.asyncio
async def test_delete_category_soft_deletes(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_service: _Stub,
) -> None:
    cat = (await client.post(
        "/api/v1/catalog/admin/categories",
        headers=admin_auth_headers,
        json={"service_id": seeded_service.id, "name": "SoftKill"},
    )).json()
    r = await client.delete(
        f"/api/v1/catalog/admin/categories/{cat['id']}", headers=admin_auth_headers
    )
    assert r.status_code == 200
    public = await client.get("/api/v1/catalog/categories")
    names = [c.get("name") for c in public.json()]
    assert "Softkill" not in names
    assert "SoftKill" not in names
