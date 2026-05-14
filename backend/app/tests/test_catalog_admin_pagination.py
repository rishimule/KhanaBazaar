# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Server-side pagination on admin products: page metadata + page_size cap."""

import pytest
from httpx import AsyncClient

from tests.conftest import _Stub


@pytest.mark.asyncio
async def test_products_pagination_page_2_returns_25_rows(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_subcategory: _Stub,
) -> None:
    for i in range(60):
        r = await client.post(
            "/api/v1/catalog/admin/products",
            headers=admin_auth_headers,
            json={
                "subcategory_id": seeded_subcategory.id,
                "name": f"P-{i:03d}",
                "base_price": 1.0,
            },
        )
        assert r.status_code == 200, r.text
    r = await client.get(
        f"/api/v1/catalog/admin/products?subcategory_id={seeded_subcategory.id}&page=2&page_size=25",
        headers=admin_auth_headers,
    )
    body = r.json()
    assert body["total"] >= 60
    assert len(body["items"]) == 25
    assert body["page"] == 2
    assert body["page_size"] == 25


@pytest.mark.asyncio
async def test_page_size_over_100_rejected(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    r = await client.get(
        "/api/v1/catalog/admin/products?page_size=500", headers=admin_auth_headers
    )
    # Pydantic enforces le=100 on Query → 422.
    assert r.status_code == 422
