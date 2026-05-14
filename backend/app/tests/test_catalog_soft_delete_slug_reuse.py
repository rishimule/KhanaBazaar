# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Soft-delete frees the slug for reuse under the same parent.

Backed by the migration's partial unique indexes (`uq_*_slug_active`)
which only enforce uniqueness when `is_active = TRUE`.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import _Stub


@pytest.mark.asyncio
async def test_soft_deleted_category_slug_reusable(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_service: _Stub,
) -> None:
    first = (await client.post(
        "/api/v1/catalog/admin/categories",
        headers=admin_auth_headers,
        json={"service_id": seeded_service.id, "name": "RecycleMe"},
    )).json()
    await client.delete(
        f"/api/v1/catalog/admin/categories/{first['id']}", headers=admin_auth_headers
    )
    r = await client.post(
        "/api/v1/catalog/admin/categories",
        headers=admin_auth_headers,
        json={"service_id": seeded_service.id, "name": "RecycleMe"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["slug"] == "recycleme"


@pytest.mark.asyncio
async def test_soft_deleted_subcategory_slug_reusable(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_category: _Stub,
) -> None:
    first = (await client.post(
        "/api/v1/catalog/admin/subcategories",
        headers=admin_auth_headers,
        json={"category_id": seeded_category.id, "name": "ReuseSub"},
    )).json()
    await client.delete(
        f"/api/v1/catalog/admin/subcategories/{first['id']}",
        headers=admin_auth_headers,
    )
    r = await client.post(
        "/api/v1/catalog/admin/subcategories",
        headers=admin_auth_headers,
        json={"category_id": seeded_category.id, "name": "ReuseSub"},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_soft_deleted_product_slug_reusable(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_subcategory: _Stub,
) -> None:
    first = (await client.post(
        "/api/v1/catalog/admin/products",
        headers=admin_auth_headers,
        json={
            "subcategory_id": seeded_subcategory.id,
            "name": "Reusable",
            "base_price": 1.0,
        },
    )).json()
    await client.delete(
        f"/api/v1/catalog/admin/products/{first['id']}", headers=admin_auth_headers
    )
    r = await client.post(
        "/api/v1/catalog/admin/products",
        headers=admin_auth_headers,
        json={
            "subcategory_id": seeded_subcategory.id,
            "name": "Reusable",
            "base_price": 1.0,
        },
    )
    assert r.status_code == 200
