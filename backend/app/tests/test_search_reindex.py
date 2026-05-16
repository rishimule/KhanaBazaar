# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
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
from app.search.reindex import (
    reindex_all,
    reindex_products,
    reindex_products_with_swap,
    reindex_search_terms,
    reindex_stores,
)
from tests._helpers import make_address


async def _seed(session: AsyncSession, n_products: int = 3) -> dict[str, int]:
    user = User(id=1001, email="bulk@kb.com", role=UserRole.Seller, is_active=True)
    session.add(user)
    await session.flush()
    biz = Address(**make_address())
    session.add(biz)
    await session.flush()
    seller = SellerProfile(
        user_id=user.id, first_name="S", phone="+919811555444",
        business_name="X", bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=biz.id,
    )
    session.add(seller)
    await session.flush()
    s_addr = Address(**make_address(latitude=19.0, longitude=72.8))
    session.add(s_addr)
    await session.flush()
    store = Store(
        name="Bulk Store", seller_profile_id=seller.id, address_id=s_addr.id,
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
    pids = []
    for i in range(n_products):
        p = MasterProduct(subcategory_id=sub.id, slug=f"p-{i}", base_price=10 + i, is_active=True)
        session.add(p)
        await session.flush()
        session.add(MasterProductTranslation(
            master_product_id=p.id, language_code="en",
            name=f"Product {i}", description="x",
        ))
        session.add(StoreInventory(
            store_id=store.id, product_id=p.id, price=10 + i, stock=5, is_available=True,
        ))
        pids.append(p.id)
    ids = {"store_id": store.id, "product_ids": pids}
    await session.commit()
    return ids


@pytest.mark.asyncio
async def test_reindex_all_populates_indexes(session: AsyncSession, meili_test_client):
    ids = await _seed(session, n_products=3)
    counts = await reindex_all(session, meili_test_client)
    assert counts["products"] == 3
    assert counts["stores"] == 1
    assert counts["search_terms"] >= 3


@pytest.mark.asyncio
async def test_reindex_products_only(session: AsyncSession, meili_test_client):
    await _seed(session, n_products=2)
    n = await reindex_products(session, meili_test_client)
    assert n == 2


@pytest.mark.asyncio
async def test_reindex_stores_only(session: AsyncSession, meili_test_client):
    await _seed(session, n_products=1)
    n = await reindex_stores(session, meili_test_client)
    assert n == 1


@pytest.mark.asyncio
async def test_reindex_search_terms(session: AsyncSession, meili_test_client):
    await _seed(session, n_products=2)
    n = await reindex_search_terms(session, meili_test_client)
    assert n >= 2


@pytest.mark.asyncio
async def test_reindex_with_swap(session: AsyncSession, meili_test_client):
    await _seed(session, n_products=2)
    # First create the products index so the swap target exists.
    n = await reindex_products_with_swap(session, meili_test_client)
    assert n == 2
    info = await meili_test_client.index("products").fetch_info()
    assert info.uid == "products"
    stats = await meili_test_client.index("products").get_stats()
    assert stats.number_of_documents >= 2
