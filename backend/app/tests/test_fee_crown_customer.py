# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Crown / is_premium propagation across the customer-facing store read paths
(storefront, store-product-detail, search store + compare, cart comparison).

Premium = the store has a non-Freebie arrangement in Active/Grace. All flags are
computed at query time via fee_gating.premium_store_ids (no Meili doc changes)."""
from datetime import date

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

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
from app.models.platform_fee import ArrangementStatus, FeeArrangement, FeeModel
from app.models.profile import SellerProfile, SellerProfileService, VerificationStatus
from app.models.store import Store, StoreInventory
from app.search.reindex import reindex_all
from app.services.price_comparison import find_alternatives
from tests._helpers import make_address


async def _paid_active(session, store_id, service_id):
    session.add(FeeArrangement(
        store_id=store_id, service_id=service_id, model=FeeModel.Subscription,
        status=ArrangementStatus.Active, valid_until=date(2026, 12, 1),
    ))
    await session.commit()


async def _stock_one_product(session, bundle):
    """Create one available inventory row under the store's service and return
    (product_id, service_id). Mirrors tests/test_fee_search_hiding."""
    cat = Category(service_id=bundle.service_id, slug="c-crown", is_active=True, sort_order=0)
    session.add(cat)
    await session.flush()
    sub = Subcategory(category_id=cat.id, slug="s-crown", is_active=True, sort_order=0)
    session.add(sub)
    await session.flush()
    prod = MasterProduct(
        subcategory_id=sub.id, slug="p-crown", is_active=True, image_url=None, base_price=10.0
    )
    session.add(prod)
    await session.flush()
    session.add(StoreInventory(
        store_id=bundle.store.id, product_id=prod.id, price=10.0, stock=5, is_available=True,
    ))
    await session.commit()
    return prod.id, bundle.service_id


@pytest.mark.asyncio
async def test_storefront_is_premium_true(
    client: AsyncClient, session: AsyncSession, approved_seller_with_store
) -> None:
    b = approved_seller_with_store
    await _paid_active(session, b.store.id, b.service_id)
    r = await client.get(f"/api/v1/stores/{b.store.id}/storefront")
    assert r.status_code == 200, r.text
    assert r.json()["store"]["is_premium"] is True


@pytest.mark.asyncio
async def test_storefront_is_premium_false_for_freebie(
    client: AsyncClient, approved_seller_with_store
) -> None:
    b = approved_seller_with_store
    r = await client.get(f"/api/v1/stores/{b.store.id}/storefront")
    assert r.status_code == 200, r.text
    assert r.json()["store"]["is_premium"] is False


@pytest.mark.asyncio
async def test_store_product_detail_is_premium(
    client: AsyncClient, session: AsyncSession, approved_seller_with_store
) -> None:
    b = approved_seller_with_store
    pid, _ = await _stock_one_product(session, b)
    await _paid_active(session, b.store.id, b.service_id)
    r = await client.get(f"/api/v1/stores/{b.store.id}/products/{pid}")
    assert r.status_code == 200, r.text
    assert r.json()["store"]["is_premium"] is True


@pytest.mark.asyncio
async def test_search_stores_is_premium(
    client: AsyncClient, session: AsyncSession, meili_test_client, approved_seller_with_store
) -> None:
    b = approved_seller_with_store
    await _stock_one_product(session, b)
    await _paid_active(session, b.store.id, b.service_id)
    await reindex_all(session, meili_test_client)
    r = await client.get("/api/v1/search/stores", params={"q": b.store.name})
    assert r.status_code == 200, r.text
    hit = next(s for s in r.json()["stores"] if s["id"] == b.store.id)
    assert hit["is_premium"] is True


@pytest.mark.asyncio
async def test_compare_offers_is_premium(
    client: AsyncClient, session: AsyncSession, meili_test_client, approved_seller_with_store
) -> None:
    b = approved_seller_with_store
    pid, _ = await _stock_one_product(session, b)
    await _paid_active(session, b.store.id, b.service_id)
    await reindex_all(session, meili_test_client)
    r = await client.get(f"/api/v1/search/products/{pid}/stores")
    assert r.status_code == 200, r.text
    offer = next(o for o in r.json()["offers"] if o["store"]["id"] == b.store.id)
    assert offer["store"]["is_premium"] is True


# ---------------------------------------------------------------------------
# Integration: find_alternatives tags each candidate with the store's premium
# status (paid Active/Grace = premium; freebie / no arrangement = not).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_alternatives_marks_premium(session: AsyncSession) -> None:
    seller_x = User(id=701, email="crown-sellerX@kb.com", role=UserRole.Seller, is_active=True)
    seller_y = User(id=702, email="crown-sellerY@kb.com", role=UserRole.Seller, is_active=True)
    session.add_all([seller_x, seller_y])
    await session.flush()

    addr_x = Address(**make_address(latitude=19.0078, longitude=72.8175, pincode="400018"))
    addr_y = Address(**make_address(latitude=19.0150, longitude=72.8200, pincode="400018"))
    session.add_all([addr_x, addr_y])
    await session.flush()

    sp_x = SellerProfile(
        user_id=seller_x.id, first_name="X", phone="+919811000701", business_name="CrownX",
        bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved, business_address_id=addr_x.id,
    )
    sp_y = SellerProfile(
        user_id=seller_y.id, first_name="Y", phone="+919811000702", business_name="CrownY",
        bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved, business_address_id=addr_y.id,
    )
    session.add_all([sp_x, sp_y])
    await session.flush()

    store_addr_x = Address(**make_address(latitude=19.0078, longitude=72.8175, pincode="400018"))
    store_addr_y = Address(**make_address(latitude=19.0150, longitude=72.8200, pincode="400018"))
    session.add_all([store_addr_x, store_addr_y])
    await session.flush()

    store_x = Store(
        name="CrownStoreX", seller_profile_id=sp_x.id, address_id=store_addr_x.id, delivery_radius_km=5.0,
    )
    store_y = Store(
        name="CrownStoreY", seller_profile_id=sp_y.id, address_id=store_addr_y.id, delivery_radius_km=5.0,
    )
    session.add_all([store_x, store_y])
    await session.flush()

    grocery = Service(slug="crown-grocery")
    session.add(grocery)
    await session.flush()
    session.add(ServiceTranslation(service_id=grocery.id, language_code="en", name="Grocery"))
    session.add_all([
        SellerProfileService(seller_profile_id=sp_x.id, service_id=grocery.id),
        SellerProfileService(seller_profile_id=sp_y.id, service_id=grocery.id),
    ])
    await session.flush()

    cat = Category(service_id=grocery.id, slug="crown-cat1")
    session.add(cat)
    await session.flush()
    session.add(CategoryTranslation(category_id=cat.id, language_code="en", name="Cat1"))
    sub = Subcategory(category_id=cat.id, slug="crown-sub1")
    session.add(sub)
    await session.flush()
    session.add(SubcategoryTranslation(subcategory_id=sub.id, language_code="en", name="Sub1"))

    product = MasterProduct(subcategory_id=sub.id, slug="crown-p1", base_price=100.0)
    session.add(product)
    await session.flush()
    session.add(MasterProductTranslation(
        master_product_id=product.id, language_code="en", name="Product1", description="Product1",
    ))
    session.add_all([
        StoreInventory(store_id=store_x.id, product_id=product.id, price=100.0, stock=10, is_available=True),
        StoreInventory(store_id=store_y.id, product_id=product.id, price=90.0, stock=10, is_available=True),
    ])
    await session.flush()

    # StoreY is a paid, live subscriber (premium); StoreX has no arrangement (freebie, not premium).
    session.add(FeeArrangement(
        store_id=store_y.id, service_id=grocery.id,
        model=FeeModel.Subscription, status=ArrangementStatus.Active,
        valid_until=date(2026, 12, 1),
    ))
    await session.flush()

    store_x_id, store_y_id, service_id, product_id = store_x.id, store_y.id, grocery.id, product.id
    await session.commit()

    result = await find_alternatives(
        session,
        source_store_id=999999,
        service_id=service_id,
        cart_items=[(product_id, 1)],
        customer_latitude=19.0080,
        customer_longitude=72.8170,
        language_code="en",
    )

    by_id = {a.id: a for a in result}
    assert by_id[store_y_id].is_premium is True
    assert by_id[store_x_id].is_premium is False
