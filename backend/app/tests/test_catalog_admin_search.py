# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Admin product search: matches English name, slug, and localized translation name."""

import pytest
from httpx import AsyncClient

from tests.conftest import _Stub


@pytest.mark.asyncio
async def test_search_matches_english_name(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_subcategory: _Stub,
) -> None:
    await client.post(
        "/api/v1/catalog/admin/products",
        headers=admin_auth_headers,
        json={
            "subcategory_id": seeded_subcategory.id,
            "name": "Basmati Rice",
            "base_price": 100.0,
        },
    )
    r = await client.get(
        "/api/v1/catalog/admin/products?q=basmati", headers=admin_auth_headers
    )
    names = [p["name"] for p in r.json()["items"]]
    assert "Basmati Rice" in names


@pytest.mark.asyncio
async def test_search_matches_slug(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_subcategory: _Stub,
) -> None:
    await client.post(
        "/api/v1/catalog/admin/products",
        headers=admin_auth_headers,
        json={
            "subcategory_id": seeded_subcategory.id,
            "name": "Special Item ABC",
            "base_price": 10.0,
        },
    )
    r = await client.get(
        "/api/v1/catalog/admin/products?q=special-item", headers=admin_auth_headers
    )
    assert any(p["slug"] == "special-item-abc" for p in r.json()["items"])


@pytest.mark.asyncio
async def test_search_matches_translation_name(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_subcategory: _Stub,
) -> None:
    prod = (await client.post(
        "/api/v1/catalog/admin/products",
        headers=admin_auth_headers,
        json={
            "subcategory_id": seeded_subcategory.id,
            "name": "Mango",
            "base_price": 60.0,
        },
    )).json()
    await client.post(
        f"/api/v1/catalog/admin/products/{prod['id']}/translations",
        headers=admin_auth_headers,
        json={"language_code": "hi", "name": "आम"},
    )
    r = await client.get(
        "/api/v1/catalog/admin/products?q=आम", headers=admin_auth_headers
    )
    assert any(item["id"] == prod["id"] for item in r.json()["items"])
