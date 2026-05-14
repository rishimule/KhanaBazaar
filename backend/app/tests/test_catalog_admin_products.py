# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Admin products CRUD with brand + unit fields and subcategory move."""

import pytest
from httpx import AsyncClient

from tests.conftest import _Stub


@pytest.mark.asyncio
async def test_create_product(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_subcategory: _Stub,
) -> None:
    r = await client.post(
        "/api/v1/catalog/admin/products",
        headers=admin_auth_headers,
        json={
            "subcategory_id": seeded_subcategory.id,
            "name": "Apple 1kg",
            "description": "Fresh apples",
            "base_price": 200.0,
            "brand": "Local Farm",
            "unit": "kg",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subcategory_id"] == seeded_subcategory.id
    assert body["slug"] == "apple-1kg"
    assert body["brand"] == "Local Farm"
    assert body["unit"] == "kg"
    assert body["description"] == "Fresh apples"


@pytest.mark.asyncio
async def test_update_product_moves_subcategory(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_subcategory: _Stub,
    seeded_category: _Stub,
) -> None:
    other_sub = (await client.post(
        "/api/v1/catalog/admin/subcategories",
        headers=admin_auth_headers,
        json={"category_id": seeded_category.id, "name": "OtherSub"},
    )).json()
    prod = (await client.post(
        "/api/v1/catalog/admin/products",
        headers=admin_auth_headers,
        json={"subcategory_id": seeded_subcategory.id, "name": "Banana", "base_price": 50.0},
    )).json()
    r = await client.put(
        f"/api/v1/catalog/admin/products/{prod['id']}",
        headers=admin_auth_headers,
        json={"subcategory_id": other_sub["id"]},
    )
    assert r.status_code == 200
    assert r.json()["subcategory_id"] == other_sub["id"]


@pytest.mark.asyncio
async def test_delete_product_soft_then_filter(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_subcategory: _Stub,
) -> None:
    prod = (await client.post(
        "/api/v1/catalog/admin/products",
        headers=admin_auth_headers,
        json={
            "subcategory_id": seeded_subcategory.id,
            "name": "Hidden",
            "base_price": 1.0,
        },
    )).json()
    r = await client.delete(
        f"/api/v1/catalog/admin/products/{prod['id']}", headers=admin_auth_headers
    )
    assert r.status_code == 200
    list_r = await client.get(
        f"/api/v1/catalog/admin/products?subcategory_id={seeded_subcategory.id}&is_active=true",
        headers=admin_auth_headers,
    )
    slugs = [p["slug"] for p in list_r.json()["items"]]
    assert "hidden" not in slugs
