# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from dataclasses import dataclass
from typing import Any

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
from app.models.profile import SellerProfile, SellerProfileService, VerificationStatus
from app.models.store import Store, StoreInventory
from tests._helpers import make_address


@dataclass
class StorefrontSeed:
    store_id: int
    product_id: int
    service_id: int


async def _seed_storefront(
    session: AsyncSession,
    *,
    seller_email: str = "storefront-seller@kb.com",
    seller_user_id: int = 42,
    en: dict[str, str] | None = None,
    hi: dict[str, str] | None = None,
    service_slug: str = "grocery",
    category_slug: str = "fruits",
    subcategory_slug: str = "apples",
    product_slug: str = "red-apple-1kg",
    inventory_price: float | None = 120.0,
    inventory_stock: int = 30,
    inventory_available: bool = True,
    store_is_active: bool = True,
) -> StorefrontSeed:
    """Build a one-store-one-product fixture and return only the ids.

    All entities live in a single commit, so the caller does not hand
    `Store`/`MasterProduct`/`Service` instances back across the commit
    boundary (which would expire their attributes and trip the
    `MissingGreenlet` path on the next attribute access in test code).
    """
    en = en or {
        "service": "Grocery",
        "category": "Fruits",
        "subcategory": "Apples",
        "product": "Red Apple 1kg",
    }

    seller_user = User(
        id=seller_user_id, email=seller_email, role=UserRole.Seller, is_active=True,
    )
    session.add(seller_user)
    await session.flush()

    biz_address = Address(**make_address())
    session.add(biz_address)
    await session.flush()

    profile = SellerProfile(
        user_id=seller_user.id,
        first_name="Test",
        last_name="Seller",
        business_name="Test Storefront",
        phone="+919811110042",
        gst_number="06ZZZZZ1111Z1Z9",
        fssai_license="11111111111111",
        bank_account_number="80100200300999",
        bank_ifsc="HDFC0009999",
        verification_status=VerificationStatus.Approved,
        business_address_id=biz_address.id,
    )
    session.add(profile)
    await session.flush()

    service = Service(slug=service_slug, sort_order=0)
    session.add(service)
    await session.flush()
    session.add(ServiceTranslation(
        service_id=service.id, language_code="en", name=en["service"],
    ))
    if hi and "service" in hi:
        session.add(ServiceTranslation(
            service_id=service.id, language_code="hi", name=hi["service"],
        ))

    category = Category(service_id=service.id, slug=category_slug, sort_order=0)
    session.add(category)
    await session.flush()
    session.add(CategoryTranslation(
        category_id=category.id, language_code="en",
        name=en["category"], description="cat-en",
    ))
    if hi and "category" in hi:
        session.add(CategoryTranslation(
            category_id=category.id, language_code="hi",
            name=hi["category"], description="cat-hi",
        ))

    subcategory = Subcategory(category_id=category.id, slug=subcategory_slug, sort_order=0)
    session.add(subcategory)
    await session.flush()
    session.add(SubcategoryTranslation(
        subcategory_id=subcategory.id, language_code="en", name=en["subcategory"],
    ))
    if hi and "subcategory" in hi:
        session.add(SubcategoryTranslation(
            subcategory_id=subcategory.id, language_code="hi", name=hi["subcategory"],
        ))

    product = MasterProduct(
        subcategory_id=subcategory.id,
        slug=product_slug,
        image_url="/images/products/red-apple.jpg",
        base_price=100,
    )
    session.add(product)
    await session.flush()
    session.add(MasterProductTranslation(
        master_product_id=product.id, language_code="en",
        name=en["product"], description="product description",
    ))
    if hi and "product" in hi:
        session.add(MasterProductTranslation(
            master_product_id=product.id, language_code="hi",
            name=hi["product"], description="हिंदी विवरण",
        ))

    store_address = Address(**make_address())
    session.add(store_address)
    await session.flush()

    store = Store(
        name="Test Storefront Mart",
        is_active=store_is_active,
        seller_profile_id=profile.id,
        address_id=store_address.id,
        delivery_radius_km=5.0,
        pin_confirmed=True,
    )
    session.add(store)
    await session.flush()
    session.add(SellerProfileService(seller_profile_id=profile.id, service_id=service.id))

    if inventory_price is not None:
        session.add(StoreInventory(
            store_id=store.id,
            product_id=product.id,
            price=inventory_price,
            stock=inventory_stock,
            is_available=inventory_available,
        ))

    # Pull IDs out before commit expires the instances.
    seed = StorefrontSeed(
        store_id=store.id,
        product_id=product.id,
        service_id=service.id,
    )
    await session.commit()
    return seed


@pytest.mark.asyncio
async def test_storefront_returns_tree_for_stocked_store(session: AsyncSession) -> None:
    seed = await _seed_storefront(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/stores/{seed.store_id}/storefront")
    assert resp.status_code == 200
    body = resp.json()
    assert body["store"]["name"] == "Test Storefront Mart"
    assert len(body["services"]) == 1
    svc = body["services"][0]
    assert svc["name"] == "Grocery"
    cat = svc["categories"][0]
    assert cat["name"] == "Fruits"
    sub = cat["subcategories"][0]
    assert sub["name"] == "Apples"
    item = sub["items"][0]
    assert item["product_name"] == "Red Apple 1kg"
    assert item["price"] == 120
    assert item["stock"] == 30


@pytest.mark.asyncio
async def test_storefront_empty_store_returns_no_services(session: AsyncSession) -> None:
    seed = await _seed_storefront(session, inventory_price=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/stores/{seed.store_id}/storefront")
    assert resp.status_code == 200
    assert resp.json()["services"] == []


@pytest.mark.asyncio
async def test_storefront_excludes_unavailable_inventory(session: AsyncSession) -> None:
    seed = await _seed_storefront(
        session,
        inventory_price=100,
        inventory_stock=0,
        inventory_available=False,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/stores/{seed.store_id}/storefront")
    assert resp.status_code == 200
    assert resp.json()["services"] == []


@pytest.mark.asyncio
async def test_storefront_404_for_unknown_store(session: AsyncSession) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/stores/99999/storefront")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_storefront_404_for_inactive_store(session: AsyncSession) -> None:
    seed = await _seed_storefront(session, store_is_active=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/stores/{seed.store_id}/storefront")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_storefront_falls_back_to_english_when_lang_missing(
    session: AsyncSession,
) -> None:
    seed = await _seed_storefront(
        session,
        en={
            "service": "Grocery EN",
            "category": "Fruits EN",
            "subcategory": "Apples EN",
            "product": "Apple EN",
        },
        inventory_price=110,
        inventory_stock=10,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            f"/api/v1/stores/{seed.store_id}/storefront",
            headers={"Accept-Language": "hi"},
        )
    assert resp.status_code == 200
    item = resp.json()["services"][0]["categories"][0]["subcategories"][0]["items"][0]
    assert item["product_name"] == "Apple EN"


@pytest.mark.asyncio
async def test_storefront_uses_locale_when_translation_present(
    session: AsyncSession,
) -> None:
    seed = await _seed_storefront(
        session,
        en={
            "service": "Grocery",
            "category": "Fruits",
            "subcategory": "Apples",
            "product": "Apple",
        },
        hi={
            "service": "किराना",
            "category": "फल",
            "subcategory": "सेब",
            "product": "सेब फल",
        },
        inventory_price=80,
        inventory_stock=12,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            f"/api/v1/stores/{seed.store_id}/storefront",
            headers={"Accept-Language": "hi"},
        )
    assert resp.status_code == 200
    svc = resp.json()["services"][0]
    assert svc["name"] == "किराना"
    assert svc["categories"][0]["name"] == "फल"
    assert svc["categories"][0]["subcategories"][0]["name"] == "सेब"
    assert svc["categories"][0]["subcategories"][0]["items"][0]["product_name"] == "सेब फल"
