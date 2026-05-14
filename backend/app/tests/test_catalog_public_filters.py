# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Public-read endpoints must exclude soft-deleted (is_active=False) catalog rows.

Soft delete sets `is_active=False`. Customer-facing reads must skip those rows
so the storefront, the catalog browse pages, and the customer catalog APIs do
not surface deactivated entities. Admin endpoints (covered separately) keep
the option to read inactive rows via `is_active=false`.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.models.catalog import (
    Category,
    CategoryTranslation,
    MasterProduct,
    MasterProductTranslation,
    Service,
    ServiceTranslation,
    Subcategory,
    SubcategoryTranslation,
)


async def _seed_chain(session: AsyncSession, *, active: bool) -> tuple[int, int, int, int]:
    """Create one service → category → subcategory → product chain with the
    same `is_active` value applied at every level (plus English translations).
    Returns the ids in order."""
    svc = Service(slug=f"svc-{'a' if active else 'i'}", is_active=active, sort_order=0)
    session.add(svc)
    await session.flush()
    assert svc.id is not None
    svc_id = svc.id
    session.add(ServiceTranslation(service_id=svc_id, language_code="en", name=f"Svc-{active}"))

    cat = Category(service_id=svc_id, slug=f"cat-{'a' if active else 'i'}", is_active=active, sort_order=0)
    session.add(cat)
    await session.flush()
    assert cat.id is not None
    cat_id = cat.id
    session.add(CategoryTranslation(category_id=cat_id, language_code="en", name=f"Cat-{active}"))

    sub = Subcategory(category_id=cat_id, slug=f"sub-{'a' if active else 'i'}", is_active=active, sort_order=0)
    session.add(sub)
    await session.flush()
    assert sub.id is not None
    sub_id = sub.id
    session.add(SubcategoryTranslation(subcategory_id=sub_id, language_code="en", name=f"Sub-{active}"))

    prod = MasterProduct(
        subcategory_id=sub_id,
        slug=f"prod-{'a' if active else 'i'}",
        base_price=10.0,
        is_active=active,
    )
    session.add(prod)
    await session.flush()
    assert prod.id is not None
    prod_id = prod.id
    session.add(
        MasterProductTranslation(
            master_product_id=prod_id,
            language_code="en",
            name=f"Prod-{active}",
            description="",
        )
    )
    await session.commit()
    return svc_id, cat_id, sub_id, prod_id


@pytest.mark.asyncio
async def test_inactive_service_excluded_from_public_list(session: AsyncSession) -> None:
    await _seed_chain(session, active=True)
    await _seed_chain(session, active=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/v1/catalog/services")
    assert r.status_code == 200
    slugs = {s["slug"] for s in r.json()}
    assert "svc-a" in slugs
    assert "svc-i" not in slugs


@pytest.mark.asyncio
async def test_inactive_category_excluded_from_public_list(session: AsyncSession) -> None:
    await _seed_chain(session, active=True)
    await _seed_chain(session, active=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/v1/catalog/categories")
    assert r.status_code == 200
    names = {c["name"] for c in r.json()}
    assert "Cat-True" in names
    assert "Cat-False" not in names


@pytest.mark.asyncio
async def test_inactive_subcategory_excluded_from_public_list(session: AsyncSession) -> None:
    await _seed_chain(session, active=True)
    await _seed_chain(session, active=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/v1/catalog/subcategories")
    assert r.status_code == 200
    names = {s["name"] for s in r.json()}
    assert "Sub-True" in names
    assert "Sub-False" not in names


@pytest.mark.asyncio
async def test_inactive_product_excluded_from_public_list(session: AsyncSession) -> None:
    await _seed_chain(session, active=True)
    await _seed_chain(session, active=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/v1/catalog/products")
    assert r.status_code == 200
    names = {p["name"] for p in r.json()}
    assert "Prod-True" in names
    assert "Prod-False" not in names
