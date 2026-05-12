# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Integration tests for GET /api/v1/stores/{store_id}/products/{product_id}.

Mirrors the seeding helper from test_storefront_endpoint.py but exposes the
seller / store / category IDs so each case can vary one axis.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.models.address import Address
from app.models.base import User, UserRole
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
from app.models.profile import (
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from tests._helpers import make_address


@dataclass
class Seed:
    store_id: int
    product_id: int
    service_id: int
    category_id: int
    subcategory_id: int
    user_id: int


async def _seed(
    session: AsyncSession,
    *,
    store_is_active: bool = True,
    inventory_available: bool = True,
    inventory_stock: int = 12,
    inventory_price: Optional[float] = 45.0,
    seed_inventory: bool = True,
    seed_hindi: bool = False,
) -> Seed:
    user = User(email="seller-pd@kb.com", role=UserRole.Seller, is_active=True)
    session.add(user)
    await session.flush()

    biz_address = Address(**make_address())
    session.add(biz_address)
    await session.flush()
    profile = SellerProfile(
        user_id=user.id,
        first_name="Seller",
        last_name=None,
        business_name="PD Test Mart",
        phone="+919811110001",
        gst_number="06AAAAA1111A1Z2",
        fssai_license="44556677889911",
        bank_account_number="80100200300701",
        bank_ifsc="HDFC0000002",
        verification_status=VerificationStatus.Approved,
        business_address_id=biz_address.id,
    )
    session.add(profile)
    await session.flush()

    service = Service(slug="grocery")
    session.add(service)
    await session.flush()
    session.add(ServiceTranslation(service_id=service.id, language_code="en", name="Grocery"))
    if seed_hindi:
        session.add(ServiceTranslation(service_id=service.id, language_code="hi", name="किराना"))

    category = Category(service_id=service.id, slug="snacks", sort_order=0)
    session.add(category)
    await session.flush()
    session.add(CategoryTranslation(
        category_id=category.id, language_code="en", name="Snacks & Chips", description="cat-en",
    ))
    if seed_hindi:
        session.add(CategoryTranslation(
            category_id=category.id, language_code="hi", name="स्नैक्स", description="cat-hi",
        ))

    subcategory = Subcategory(category_id=category.id, slug="chips", sort_order=0)
    session.add(subcategory)
    await session.flush()
    session.add(SubcategoryTranslation(
        subcategory_id=subcategory.id, language_code="en", name="Chips",
    ))
    if seed_hindi:
        session.add(SubcategoryTranslation(
            subcategory_id=subcategory.id, language_code="hi", name="चिप्स",
        ))

    product = MasterProduct(
        subcategory_id=subcategory.id,
        slug="kurkure-masala-munch-90g",
        image_url="/images/products/kurkure.jpg",
        base_price=50,
    )
    session.add(product)
    await session.flush()
    session.add(MasterProductTranslation(
        master_product_id=product.id, language_code="en",
        name="Kurkure Masala Munch 90g", description="Tangy masala corn puffs.",
    ))
    if seed_hindi:
        session.add(MasterProductTranslation(
            master_product_id=product.id, language_code="hi",
            name="कुरकुरे मसाला मंच 90g", description="चटपटे मसालेदार कॉर्न पफ।",
        ))

    store_address = Address(**make_address())
    session.add(store_address)
    await session.flush()
    store = Store(
        name="Sai Kirana",
        is_active=store_is_active,
        seller_profile_id=profile.id,
        address_id=store_address.id,
        delivery_radius_km=5.0,
        pin_confirmed=True,
    )
    session.add(store)
    await session.flush()
    session.add(SellerProfileService(seller_profile_id=profile.id, service_id=service.id))

    if seed_inventory and inventory_price is not None:
        session.add(StoreInventory(
            store_id=store.id,
            product_id=product.id,
            price=inventory_price,
            stock=inventory_stock,
            is_available=inventory_available,
        ))

    seed = Seed(
        store_id=store.id,  # type: ignore[arg-type]
        product_id=product.id,  # type: ignore[arg-type]
        service_id=service.id,  # type: ignore[arg-type]
        category_id=category.id,  # type: ignore[arg-type]
        subcategory_id=subcategory.id,  # type: ignore[arg-type]
        user_id=user.id,  # type: ignore[arg-type]
    )
    await session.commit()
    return seed


@pytest.mark.asyncio
async def test_returns_full_payload_for_available_product(session: AsyncSession) -> None:
    seed = await _seed(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/stores/{seed.store_id}/products/{seed.product_id}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["store"] == {"id": seed.store_id, "name": "Sai Kirana"}
    assert body["service"] == {"id": seed.service_id, "name": "Grocery"}
    inv = body["inventory"]
    assert inv["store_id"] == seed.store_id
    assert inv["product_id"] == seed.product_id
    assert inv["is_available"] is True
    assert inv["stock"] == 12
    assert float(inv["price"]) == 45.0
    prod = inv["product"]
    assert prod["name"] == "Kurkure Masala Munch 90g"
    assert prod["description"] == "Tangy masala corn puffs."
    assert prod["category_id"] == seed.category_id
    assert prod["subcategory_id"] == seed.subcategory_id
    assert prod["subcategory_name"] == "Chips"
    assert body["breadcrumb"] == {
        "service_id": seed.service_id,
        "service_name": "Grocery",
        "category_id": seed.category_id,
        "category_name": "Snacks & Chips",
        "subcategory_id": seed.subcategory_id,
        "subcategory_name": "Chips",
    }


@pytest.mark.asyncio
async def test_localizes_breadcrumb_when_accept_language_is_hindi(session: AsyncSession) -> None:
    seed = await _seed(session, seed_hindi=True)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            f"/api/v1/stores/{seed.store_id}/products/{seed.product_id}",
            headers={"Accept-Language": "hi"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["service"]["name"] == "किराना"
    assert body["breadcrumb"]["service_name"] == "किराना"
    assert body["breadcrumb"]["category_name"] == "स्नैक्स"
    assert body["breadcrumb"]["subcategory_name"] == "चिप्स"
    assert body["inventory"]["product"]["name"] == "कुरकुरे मसाला मंच 90g"


@pytest.mark.asyncio
async def test_unknown_store_returns_404(session: AsyncSession) -> None:
    seed = await _seed(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/stores/9999/products/{seed.product_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_inactive_store_returns_404(session: AsyncSession) -> None:
    seed = await _seed(session, store_is_active=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/stores/{seed.store_id}/products/{seed.product_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_product_not_in_inventory_returns_404(session: AsyncSession) -> None:
    seed = await _seed(session, seed_inventory=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/stores/{seed.store_id}/products/{seed.product_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unavailable_product_returns_payload_with_is_available_false(
    session: AsyncSession,
) -> None:
    seed = await _seed(session, inventory_available=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/stores/{seed.store_id}/products/{seed.product_id}")
    assert resp.status_code == 200
    assert resp.json()["inventory"]["is_available"] is False


@pytest.mark.asyncio
async def test_out_of_stock_returns_payload_with_stock_zero(session: AsyncSession) -> None:
    seed = await _seed(session, inventory_stock=0)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/stores/{seed.store_id}/products/{seed.product_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["inventory"]["stock"] == 0
    assert body["inventory"]["is_available"] is True
