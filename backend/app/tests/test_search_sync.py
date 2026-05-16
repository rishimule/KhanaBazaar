# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from unittest.mock import patch

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import (
    Category,
    CategoryTranslation,
    MasterProduct,
    MasterProductTranslation,
    Service,
    Subcategory,
    SubcategoryTranslation,
)
from app.models.profile import SellerProfile, VerificationStatus
from app.models.store import Store, StoreInventory
from app.search.hooks import register_search_hooks
from app.search.tasks import (
    _do_reindex_product,
    _do_reindex_products_by_category,
    _do_reindex_products_by_subcategory,
    _do_reindex_products_for_store,
    _do_reindex_store,
)
from tests._helpers import make_address


# Hooks register at import in app/__init__.py already; ensure idempotent re-call works.
register_search_hooks()


async def _seed_full(session: AsyncSession):
    user = User(id=901, email="sync@kb.com", role=UserRole.Seller, is_active=True)
    session.add(user)
    await session.flush()
    biz_addr = Address(**make_address(pincode="500001"))
    session.add(biz_addr)
    await session.flush()
    seller = SellerProfile(
        user_id=user.id, first_name="S", phone="+919811222333",
        business_name="X", bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=biz_addr.id,
    )
    session.add(seller)
    await session.flush()
    store_addr = Address(**make_address(latitude=19.07, longitude=72.87, pincode="500002"))
    session.add(store_addr)
    await session.flush()
    store = Store(
        name="Sync Store", seller_profile_id=seller.id, address_id=store_addr.id,
        is_active=True, delivery_radius_km=5,
    )
    session.add(store)
    await session.flush()
    svc = Service(slug="grocery", is_active=True)
    session.add(svc)
    await session.flush()
    cat = Category(service_id=svc.id, slug="dairy", is_active=True)
    session.add(cat)
    await session.flush()
    session.add(CategoryTranslation(category_id=cat.id, language_code="en", name="Dairy"))
    sub = Subcategory(category_id=cat.id, slug="milk", is_active=True)
    session.add(sub)
    await session.flush()
    session.add(SubcategoryTranslation(subcategory_id=sub.id, language_code="en", name="Milk"))
    product = MasterProduct(
        subcategory_id=sub.id, slug="milk-1l", base_price=68, is_active=True,
    )
    session.add(product)
    await session.flush()
    session.add(MasterProductTranslation(
        master_product_id=product.id, language_code="en", name="Milk 1L", description=".",
    ))
    session.add(StoreInventory(
        store_id=store.id, product_id=product.id, price=70, stock=10, is_available=True,
    ))
    ids = {
        "store_id": store.id, "product_id": product.id,
        "category_id": cat.id, "subcategory_id": sub.id,
    }
    await session.commit()
    return ids


@pytest.mark.asyncio
async def test_async_helper_reindexes_product(session: AsyncSession, meili_test_client):
    ids = await _seed_full(session)
    await _do_reindex_product(ids["product_id"])
    doc = await meili_test_client.index("products").get_document(ids["product_id"])
    # SDK returns dict-like results from get_document
    assert doc["id"] == ids["product_id"]


@pytest.mark.asyncio
async def test_async_helper_reindexes_store(session: AsyncSession, meili_test_client):
    ids = await _seed_full(session)
    await _do_reindex_store(ids["store_id"])
    doc = await meili_test_client.index("stores").get_document(ids["store_id"])
    assert doc["name"] == "Sync Store"


@pytest.mark.asyncio
async def test_async_helper_fans_out_store_products(session: AsyncSession):
    ids = await _seed_full(session)
    with patch("app.search.tasks.reindex_master_product.delay") as spy:
        pids = await _do_reindex_products_for_store(ids["store_id"])
    assert pids == [ids["product_id"]]
    spy.assert_called_with(ids["product_id"])


@pytest.mark.asyncio
async def test_async_helper_fans_out_subcategory(session: AsyncSession):
    ids = await _seed_full(session)
    with patch("app.search.tasks.reindex_master_product.delay") as spy:
        pids = await _do_reindex_products_by_subcategory(ids["subcategory_id"])
    assert pids == [ids["product_id"]]
    spy.assert_called_with(ids["product_id"])


@pytest.mark.asyncio
async def test_async_helper_fans_out_category(session: AsyncSession):
    ids = await _seed_full(session)
    with patch("app.search.tasks.reindex_products_by_subcategory.delay") as spy:
        subs = await _do_reindex_products_by_category(ids["category_id"])
    assert subs == [ids["subcategory_id"]]
    spy.assert_called_with(ids["subcategory_id"])


@pytest.mark.asyncio
async def test_hook_enqueues_on_product_update(session: AsyncSession):
    ids = await _seed_full(session)
    with patch("app.search.tasks.reindex_master_product.delay") as spy:
        product = (await session.get(MasterProduct, ids["product_id"]))
        product.brand = "NewBrand"
        await session.commit()
    spy.assert_any_call(ids["product_id"])


@pytest.mark.asyncio
async def test_hook_enqueues_on_inventory_update(session: AsyncSession):
    ids = await _seed_full(session)
    with patch("app.search.tasks.reindex_master_product.delay") as spy:
        inv = (await session.execute(
            __import__("sqlalchemy").select(StoreInventory).where(
                StoreInventory.product_id == ids["product_id"]
            )
        )).scalar_one()
        inv.price = 99.0
        await session.commit()
    spy.assert_any_call(ids["product_id"])


@pytest.mark.asyncio
async def test_hook_enqueues_on_store_update(session: AsyncSession):
    ids = await _seed_full(session)
    with patch("app.search.tasks.reindex_store.delay") as s_spy, \
         patch("app.search.tasks.reindex_products_for_store.delay") as p_spy:
        store = await session.get(Store, ids["store_id"])
        store.name = "Updated Name"
        await session.commit()
    s_spy.assert_any_call(ids["store_id"])
    p_spy.assert_any_call(ids["store_id"])
