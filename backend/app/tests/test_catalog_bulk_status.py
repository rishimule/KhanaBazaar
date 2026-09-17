# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Multi-select activate/deactivate from the admin catalog table.

This is the "bulk delete" half of the feature: CSV import is upsert-only and
never deactivates, so taking rows offline is always this explicitly confirmed
action instead.
"""

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import Category, MasterProduct, Service, Subcategory
from tests.catalog_csv_fixtures import row, upload_and_apply
from tests.conftest import _Stub

pytestmark = pytest.mark.asyncio

BULK = "/api/v1/catalog/admin/bulk/status"


async def _seed_products(
    client: AsyncClient, headers: dict[str, str], count: int
) -> None:
    await upload_and_apply(
        client, headers, [row(product_slug=f"p-{i}") for i in range(count)]
    )


async def test_bulk_deactivate_products(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    await _seed_products(client, admin_auth_headers, 3)
    products = (await session.exec(select(MasterProduct))).all()
    target_ids = [p.id for p in products[:2]]

    r = await client.post(
        BULK,
        headers=admin_auth_headers,
        json={"entity": "product", "ids": target_ids, "is_active": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated"] == 2
    assert body["unchanged"] == []
    assert body["not_found"] == []

    for product in products:
        await session.refresh(product)
    by_id = {p.id: p for p in products}
    assert by_id[target_ids[0]].is_active is False
    assert by_id[target_ids[1]].is_active is False
    remaining = [p for p in products if p.id not in target_ids][0]
    assert remaining.is_active is True


async def test_bulk_reactivate_products(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    await _seed_products(client, admin_auth_headers, 2)
    ids = [p.id for p in (await session.exec(select(MasterProduct))).all()]

    await client.post(
        BULK,
        headers=admin_auth_headers,
        json={"entity": "product", "ids": ids, "is_active": False},
    )
    r = await client.post(
        BULK,
        headers=admin_auth_headers,
        json={"entity": "product", "ids": ids, "is_active": True},
    )
    assert r.json()["updated"] == 2
    for product in (await session.exec(select(MasterProduct))).all():
        await session.refresh(product)
        assert product.is_active is True


async def test_already_in_state_is_reported_as_unchanged(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    """So the UI can explain "12 selected, 9 updated" rather than losing 3."""
    await _seed_products(client, admin_auth_headers, 2)
    ids = [p.id for p in (await session.exec(select(MasterProduct))).all()]

    await client.post(
        BULK,
        headers=admin_auth_headers,
        json={"entity": "product", "ids": ids[:1], "is_active": False},
    )
    r = await client.post(
        BULK,
        headers=admin_auth_headers,
        json={"entity": "product", "ids": ids, "is_active": False},
    )
    body = r.json()
    assert body["updated"] == 1
    assert body["unchanged"] == [ids[0]]


async def test_unknown_ids_reported_not_fatal(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    await _seed_products(client, admin_auth_headers, 1)
    real = (await session.exec(select(MasterProduct))).all()[0].id

    r = await client.post(
        BULK,
        headers=admin_auth_headers,
        json={"entity": "product", "ids": [real, 987654], "is_active": False},
    )
    assert r.status_code == 200
    assert r.json()["updated"] == 1
    assert r.json()["not_found"] == [987654]


async def test_duplicate_ids_are_deduped(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    await _seed_products(client, admin_auth_headers, 1)
    real = (await session.exec(select(MasterProduct))).all()[0].id
    r = await client.post(
        BULK,
        headers=admin_auth_headers,
        json={"entity": "product", "ids": [real, real, real], "is_active": False},
    )
    assert r.json()["updated"] == 1
    assert r.json()["unchanged"] == []


@pytest.mark.parametrize(
    "entity,model",
    [
        ("service", Service),
        ("category", Category),
        ("subcategory", Subcategory),
        ("product", MasterProduct),
    ],
)
async def test_works_at_every_level(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
    entity: str,
    model: type,
) -> None:
    await _seed_products(client, admin_auth_headers, 1)
    rows = (await session.exec(select(model))).all()  # type: ignore[call-overload]
    assert rows, f"nothing seeded for {entity}"
    ids = [r.id for r in rows]

    r = await client.post(
        BULK,
        headers=admin_auth_headers,
        json={"entity": entity, "ids": ids, "is_active": False},
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == len(ids)
    for entry in rows:
        await session.refresh(entry)
        assert entry.is_active is False


async def test_deactivating_a_parent_does_not_cascade(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
) -> None:
    """Matches the per-row Deactivate button, which warns with a child count
    but leaves children alone."""
    await _seed_products(client, admin_auth_headers, 2)
    category = (await session.exec(select(Category))).all()[0]

    await client.post(
        BULK,
        headers=admin_auth_headers,
        json={"entity": "category", "ids": [category.id], "is_active": False},
    )
    for product in (await session.exec(select(MasterProduct))).all():
        await session.refresh(product)
        assert product.is_active is True


async def test_empty_ids_rejected(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    r = await client.post(
        BULK,
        headers=admin_auth_headers,
        json={"entity": "product", "ids": [], "is_active": False},
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "ids_required"


async def test_row_limit_enforced(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    r = await client.post(
        BULK,
        headers=admin_auth_headers,
        json={"entity": "product", "ids": list(range(1, 502)), "is_active": False},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "ROW_LIMIT"


async def test_unknown_entity_rejected(
    client: AsyncClient, admin_auth_headers: dict[str, str], persisted_admin: object
) -> None:
    r = await client.post(
        BULK,
        headers=admin_auth_headers,
        json={"entity": "banana", "ids": [1], "is_active": False},
    )
    assert r.status_code == 422


async def test_deactivated_products_disappear_from_the_public_catalog(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    persisted_admin: object,
    session: AsyncSession,
    seeded_subcategory: _Stub,
) -> None:
    """The point of the feature: `is_active=False` hides rows from customers."""
    created = await client.post(
        "/api/v1/catalog/admin/products",
        headers=admin_auth_headers,
        json={
            "subcategory_id": seeded_subcategory.id,
            "name": "Hide Me",
            "base_price": 10.0,
        },
    )
    assert created.status_code == 200, created.text
    product_id = created.json()["id"]

    # The admin list defaults to no is_active filter (see the router docstring);
    # the UI passes is_active=true, which is the view this must affect.
    active_url = (
        "/api/v1/catalog/admin/products"
        f"?subcategory_id={seeded_subcategory.id}&is_active=true"
    )
    assert product_id in {
        i["id"] for i in (await client.get(active_url, headers=admin_auth_headers)).json()["items"]
    }
    public_before = await client.get("/api/v1/catalog/products")
    assert product_id in {i["id"] for i in public_before.json()}

    await client.post(
        BULK,
        headers=admin_auth_headers,
        json={"entity": "product", "ids": [product_id], "is_active": False},
    )

    after = await client.get(active_url, headers=admin_auth_headers)
    assert product_id not in {i["id"] for i in after.json()["items"]}

    # And it is gone from the customer-facing catalog, which is the point.
    public_after = await client.get("/api/v1/catalog/products")
    assert product_id not in {i["id"] for i in public_after.json()}

    # Still visible under the inactive filter, so the operator can restore it.
    inactive_url = (
        "/api/v1/catalog/admin/products"
        f"?subcategory_id={seeded_subcategory.id}&is_active=false"
    )
    restorable = await client.get(inactive_url, headers=admin_auth_headers)
    assert product_id in {i["id"] for i in restorable.json()["items"]}
