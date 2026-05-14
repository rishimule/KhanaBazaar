# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Admin subcategories CRUD: create, move between categories, slug-clash
detection on move, soft delete cascade to public reads."""

import pytest
from httpx import AsyncClient

from tests.conftest import _Stub


@pytest.mark.asyncio
async def test_create_subcategory(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_category: _Stub,
) -> None:
    r = await client.post(
        "/api/v1/catalog/admin/subcategories",
        headers=admin_auth_headers,
        json={"category_id": seeded_category.id, "name": "Leafy Greens"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["category_id"] == seeded_category.id
    assert body["slug"] == "leafy-greens"


@pytest.mark.asyncio
async def test_move_subcategory_slug_clash_409(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_category: _Stub,
) -> None:
    other = (await client.post(
        "/api/v1/catalog/admin/categories",
        headers=admin_auth_headers,
        json={"service_id": seeded_category.service_id, "name": "OtherCat"},
    )).json()
    await client.post(
        "/api/v1/catalog/admin/subcategories",
        headers=admin_auth_headers,
        json={"category_id": seeded_category.id, "name": "Apples"},
    )
    target = (await client.post(
        "/api/v1/catalog/admin/subcategories",
        headers=admin_auth_headers,
        json={"category_id": other["id"], "name": "Apples"},
    )).json()
    r = await client.put(
        f"/api/v1/catalog/admin/subcategories/{target['id']}",
        headers=admin_auth_headers,
        json={"category_id": seeded_category.id},
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "slug_exists_in_destination"


@pytest.mark.asyncio
async def test_delete_subcategory_soft(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_category: _Stub,
) -> None:
    sub = (await client.post(
        "/api/v1/catalog/admin/subcategories",
        headers=admin_auth_headers,
        json={"category_id": seeded_category.id, "name": "ToGo"},
    )).json()
    r = await client.delete(
        f"/api/v1/catalog/admin/subcategories/{sub['id']}", headers=admin_auth_headers
    )
    assert r.status_code == 200
    public = await client.get("/api/v1/catalog/subcategories")
    slugs = [s.get("slug") for s in public.json()]
    assert "togo" not in slugs
