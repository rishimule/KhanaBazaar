# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from dataclasses import dataclass
from typing import AsyncGenerator

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
class PreviewSeed:
    store_id: int
    grocery_service_id: int
    empty_service_id: int


async def _seed_preview(session: AsyncSession) -> PreviewSeed:
    """One active store, grocery service with two products (apple in stock,
    banana out of stock, both available) and a second 'pharmacy' service with
    no products. Returns ids only (instances expire on commit)."""
    seller = User(id=901, email="prev-seller@kb.com", role=UserRole.Seller, is_active=True)
    session.add(seller)
    await session.flush()

    biz = Address(**make_address())
    session.add(biz)
    await session.flush()

    profile = SellerProfile(
        user_id=seller.id,
        first_name="Prev",
        last_name="Seller",
        business_name="Preview Mart",
        phone="+919811119001",
        gst_number="06PPPPP1111P1Z9",
        fssai_license="22222222222222",
        bank_account_number="80100200300901",
        bank_ifsc="HDFC0009901",
        verification_status=VerificationStatus.Approved,
        business_address_id=biz.id,
    )
    session.add(profile)
    await session.flush()

    grocery = Service(slug="grocery", sort_order=0)
    pharmacy = Service(slug="pharmacy", sort_order=1)
    session.add(grocery)
    session.add(pharmacy)
    await session.flush()
    session.add(ServiceTranslation(service_id=grocery.id, language_code="en", name="Grocery"))
    session.add(ServiceTranslation(service_id=pharmacy.id, language_code="en", name="Pharmacy"))

    category = Category(service_id=grocery.id, slug="fruits", sort_order=0)
    session.add(category)
    await session.flush()
    session.add(CategoryTranslation(
        category_id=category.id, language_code="en", name="Fruits", description="c",
    ))

    sub = Subcategory(category_id=category.id, slug="fresh", sort_order=0)
    session.add(sub)
    await session.flush()
    session.add(SubcategoryTranslation(
        subcategory_id=sub.id, language_code="en", name="Fresh",
    ))

    apple = MasterProduct(subcategory_id=sub.id, slug="apple-1kg", base_price=100)
    banana = MasterProduct(subcategory_id=sub.id, slug="banana-1kg", base_price=50)
    session.add(apple)
    session.add(banana)
    await session.flush()
    session.add(MasterProductTranslation(
        master_product_id=apple.id, language_code="en", name="Apple 1kg", description="d",
    ))
    session.add(MasterProductTranslation(
        master_product_id=banana.id, language_code="en", name="Banana 1kg", description="d",
    ))

    store_addr = Address(**make_address())
    session.add(store_addr)
    await session.flush()
    store = Store(
        name="Preview Mart",
        is_active=True,
        seller_profile_id=profile.id,
        address_id=store_addr.id,
        delivery_radius_km=5.0,
        pin_confirmed=True,
    )
    session.add(store)
    await session.flush()
    session.add(SellerProfileService(seller_profile_id=profile.id, service_id=grocery.id))
    session.add(SellerProfileService(seller_profile_id=profile.id, service_id=pharmacy.id))

    # banana is out of stock, apple in stock — both available.
    session.add(StoreInventory(
        store_id=store.id, product_id=banana.id, price=50, stock=0, is_available=True,
    ))
    session.add(StoreInventory(
        store_id=store.id, product_id=apple.id, price=100, stock=30, is_available=True,
    ))

    assert store.id is not None
    assert grocery.id is not None
    assert pharmacy.id is not None
    seed = PreviewSeed(
        store_id=store.id,
        grocery_service_id=grocery.id,
        empty_service_id=pharmacy.id,
    )
    await session.commit()
    return seed


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_preview_returns_localized_in_stock_first(
    session: AsyncSession, client: AsyncClient,
) -> None:
    seed = await _seed_preview(session)
    resp = await client.get(
        f"/api/v1/stores/{seed.store_id}/preview",
        params={"service_id": seed.grocery_service_id, "limit": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    # In-stock apple sorts before out-of-stock banana.
    assert body[0]["product"]["name"] == "Apple 1kg"
    assert body[0]["stock"] == 30
    assert body[1]["product"]["name"] == "Banana 1kg"
    # Shape ProductCard consumes.
    assert body[0]["product"]["category_id"] is not None
    assert "subcategory_name" in body[0]["product"]


async def test_preview_limit_caps_results(
    session: AsyncSession, client: AsyncClient,
) -> None:
    seed = await _seed_preview(session)
    resp = await client.get(
        f"/api/v1/stores/{seed.store_id}/preview",
        params={"service_id": seed.grocery_service_id, "limit": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["product"]["name"] == "Apple 1kg"


async def test_preview_limit_out_of_range_is_422(
    session: AsyncSession, client: AsyncClient,
) -> None:
    seed = await _seed_preview(session)
    for bad in (0, 21):
        resp = await client.get(
            f"/api/v1/stores/{seed.store_id}/preview",
            params={"service_id": seed.grocery_service_id, "limit": bad},
        )
        assert resp.status_code == 422


async def test_preview_unknown_store_is_404(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/stores/999999/preview", params={"service_id": 1},
    )
    assert resp.status_code == 404


async def test_preview_service_without_products_is_empty(
    session: AsyncSession, client: AsyncClient,
) -> None:
    seed = await _seed_preview(session)
    resp = await client.get(
        f"/api/v1/stores/{seed.store_id}/preview",
        params={"service_id": seed.empty_service_id},
    )
    assert resp.status_code == 200
    assert resp.json() == []
