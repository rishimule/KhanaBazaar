# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Translation upsert covers all four catalog entity types.

Empty strings → delete row → public read falls back to English.
Unknown language code → 400. Subsequent upsert overrides previous value."""

import pytest
from httpx import AsyncClient

from tests.conftest import _Stub


@pytest.mark.asyncio
async def test_upsert_service_translation_creates(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    svc = (await client.post(
        "/api/v1/catalog/admin/services",
        headers=admin_auth_headers,
        json={"name": "Grocery2"},
    )).json()
    r = await client.post(
        f"/api/v1/catalog/admin/services/{svc['id']}/translations",
        headers=admin_auth_headers,
        json={"language_code": "hi", "name": "किराना2"},
    )
    assert r.status_code == 200, r.text
    fetched = (await client.get(
        "/api/v1/catalog/admin/services", headers=admin_auth_headers
    )).json()
    item = next(s for s in fetched["items"] if s["id"] == svc["id"])
    by_lang = {t["language_code"]: t["name"] for t in item["translations"]}
    assert by_lang.get("hi") == "किराना2"


@pytest.mark.asyncio
async def test_upsert_service_translation_updates_existing(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    svc = (await client.post(
        "/api/v1/catalog/admin/services",
        headers=admin_auth_headers,
        json={"name": "GroceryX"},
    )).json()
    await client.post(
        f"/api/v1/catalog/admin/services/{svc['id']}/translations",
        headers=admin_auth_headers,
        json={"language_code": "hi", "name": "Old"},
    )
    r = await client.post(
        f"/api/v1/catalog/admin/services/{svc['id']}/translations",
        headers=admin_auth_headers,
        json={"language_code": "hi", "name": "Updated"},
    )
    assert r.status_code == 200
    fetched = (await client.get(
        "/api/v1/catalog/admin/services", headers=admin_auth_headers
    )).json()
    item = next(s for s in fetched["items"] if s["id"] == svc["id"])
    by_lang = {t["language_code"]: t["name"] for t in item["translations"]}
    assert by_lang["hi"] == "Updated"


@pytest.mark.asyncio
async def test_upsert_translation_unknown_language_400(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    svc = (await client.post(
        "/api/v1/catalog/admin/services",
        headers=admin_auth_headers,
        json={"name": "Grocery3"},
    )).json()
    r = await client.post(
        f"/api/v1/catalog/admin/services/{svc['id']}/translations",
        headers=admin_auth_headers,
        json={"language_code": "xx", "name": "..."},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "unknown_language"


@pytest.mark.asyncio
async def test_clear_translation_with_empty_strings_deletes_row(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    svc = (await client.post(
        "/api/v1/catalog/admin/services",
        headers=admin_auth_headers,
        json={"name": "Grocery4"},
    )).json()
    await client.post(
        f"/api/v1/catalog/admin/services/{svc['id']}/translations",
        headers=admin_auth_headers,
        json={"language_code": "hi", "name": "Will be cleared"},
    )
    r = await client.post(
        f"/api/v1/catalog/admin/services/{svc['id']}/translations",
        headers=admin_auth_headers,
        json={"language_code": "hi", "name": "", "description": ""},
    )
    assert r.status_code == 200
    fetched = (await client.get(
        "/api/v1/catalog/admin/services", headers=admin_auth_headers
    )).json()
    item = next(s for s in fetched["items"] if s["id"] == svc["id"])
    langs = [t["language_code"] for t in item["translations"]]
    assert "hi" not in langs


@pytest.mark.asyncio
async def test_upsert_category_translation(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_service: _Stub,
) -> None:
    cat = (await client.post(
        "/api/v1/catalog/admin/categories",
        headers=admin_auth_headers,
        json={"service_id": seeded_service.id, "name": "Veggies"},
    )).json()
    r = await client.post(
        f"/api/v1/catalog/admin/categories/{cat['id']}/translations",
        headers=admin_auth_headers,
        json={"language_code": "mr", "name": "भाज्या"},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_upsert_subcategory_translation(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_category: _Stub,
) -> None:
    sub = (await client.post(
        "/api/v1/catalog/admin/subcategories",
        headers=admin_auth_headers,
        json={"category_id": seeded_category.id, "name": "Tomatoes"},
    )).json()
    r = await client.post(
        f"/api/v1/catalog/admin/subcategories/{sub['id']}/translations",
        headers=admin_auth_headers,
        json={"language_code": "gu", "name": "ટામેટા"},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_upsert_product_translation(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_subcategory: _Stub,
) -> None:
    prod = (await client.post(
        "/api/v1/catalog/admin/products",
        headers=admin_auth_headers,
        json={
            "subcategory_id": seeded_subcategory.id,
            "name": "Lemon",
            "base_price": 5.0,
        },
    )).json()
    r = await client.post(
        f"/api/v1/catalog/admin/products/{prod['id']}/translations",
        headers=admin_auth_headers,
        json={"language_code": "pa", "name": "ਨਿੰਬੂ"},
    )
    assert r.status_code == 200
