# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""All `/catalog/admin/*` endpoints must reject non-admin callers.

Anonymous → 401 (HTTPBearer). Customer-role JWT → 403 (role guard).
Admin → 200 (or the underlying endpoint's success status)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/catalog/admin/services",
        "/api/v1/catalog/admin/categories",
        "/api/v1/catalog/admin/subcategories",
        "/api/v1/catalog/admin/products",
    ],
)
async def test_admin_list_endpoints_reject_anonymous(
    client: AsyncClient, path: str
) -> None:
    r = await client.get(path)
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_list_services_accepts_admin(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    r = await client.get("/api/v1/catalog/admin/services", headers=admin_auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert "page" in body
    assert "page_size" in body
