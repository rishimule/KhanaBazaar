# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Admin services CRUD: create, paginated list, update, soft delete, and
is_active filter behavior."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_service(client: AsyncClient, admin_auth_headers: dict[str, str]) -> None:
    r = await client.post(
        "/api/v1/catalog/admin/services",
        headers=admin_auth_headers,
        json={"name": "Pharmacy", "description": "Local pharmacy", "sort_order": 5},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slug"] == "pharmacy"
    assert body["name"] == "Pharmacy"
    assert body["is_active"] is True
    assert body["sort_order"] == 5


@pytest.mark.asyncio
async def test_list_services_paged_response_shape(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    for i in range(3):
        await client.post(
            "/api/v1/catalog/admin/services",
            headers=admin_auth_headers,
            json={"name": f"Service-{i}"},
        )
    r = await client.get(
        "/api/v1/catalog/admin/services?page=1&page_size=2",
        headers=admin_auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 3
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 2


@pytest.mark.asyncio
async def test_update_service(client: AsyncClient, admin_auth_headers: dict[str, str]) -> None:
    created = (await client.post(
        "/api/v1/catalog/admin/services",
        headers=admin_auth_headers,
        json={"name": "Bakery"},
    )).json()
    r = await client.put(
        f"/api/v1/catalog/admin/services/{created['id']}",
        headers=admin_auth_headers,
        json={"name": "Bakery & Café", "sort_order": 9},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Bakery & Café"
    assert body["sort_order"] == 9


@pytest.mark.asyncio
async def test_delete_service_soft_deletes(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    created = (await client.post(
        "/api/v1/catalog/admin/services",
        headers=admin_auth_headers,
        json={"name": "FloristTemp"},
    )).json()
    r = await client.delete(
        f"/api/v1/catalog/admin/services/{created['id']}",
        headers=admin_auth_headers,
    )
    assert r.status_code == 200
    public = await client.get("/api/v1/catalog/services")
    slugs = [s["slug"] for s in public.json()]
    assert "floristtemp" not in slugs


@pytest.mark.asyncio
async def test_list_services_filter_is_active(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    created = (await client.post(
        "/api/v1/catalog/admin/services",
        headers=admin_auth_headers,
        json={"name": "TempInactive"},
    )).json()
    await client.delete(
        f"/api/v1/catalog/admin/services/{created['id']}",
        headers=admin_auth_headers,
    )

    active = await client.get(
        "/api/v1/catalog/admin/services?is_active=true", headers=admin_auth_headers
    )
    inactive = await client.get(
        "/api/v1/catalog/admin/services?is_active=false", headers=admin_auth_headers
    )
    active_slugs = [s["slug"] for s in active.json()["items"]]
    inactive_slugs = [s["slug"] for s in inactive.json()["items"]]
    assert "tempinactive" not in active_slugs
    assert "tempinactive" in inactive_slugs


@pytest.mark.asyncio
async def test_create_service_slug_conflict_409(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    await client.post(
        "/api/v1/catalog/admin/services",
        headers=admin_auth_headers,
        json={"name": "Stationery"},
    )
    r = await client.post(
        "/api/v1/catalog/admin/services",
        headers=admin_auth_headers,
        json={"name": "Stationery"},
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "slug_exists"
