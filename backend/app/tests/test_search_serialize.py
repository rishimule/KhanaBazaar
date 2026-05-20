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
    ServiceTranslation,
    Subcategory,
    SubcategoryTranslation,
)
from app.models.profile import SellerProfile, VerificationStatus
from app.models.store import Store, StoreInventory
from app.search.serialize import (
    build_product_document,
    build_search_term_docs,
    build_store_document,
)
from tests._helpers import make_address


async def _seed_chain(session: AsyncSession, *, with_inventory: bool = True):
    user = User(id=701, email="seed-search@kb.com", role=UserRole.Seller, is_active=True)
    session.add(user)
    await session.flush()
    addr = Address(**make_address(pincode="560210"))
    session.add(addr)
    await session.flush()
    seller = SellerProfile(
        user_id=user.id, first_name="S", phone="+919811000999",
        business_name="X", bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=addr.id,
    )
    session.add(seller)
    await session.flush()
    store_addr = Address(**make_address(pincode="560211", latitude=19.07, longitude=72.87))
    session.add(store_addr)
    await session.flush()
    store = Store(
        name="Raj Kirana", seller_profile_id=seller.id, address_id=store_addr.id,
        is_active=True, delivery_radius_km=5,
    )
    session.add(store)
    await session.flush()

    svc = Service(slug="grocery", is_active=True)
    session.add(svc)
    await session.flush()
    session.add(ServiceTranslation(service_id=svc.id, language_code="en", name="Grocery"))

    cat = Category(service_id=svc.id, slug="dairy", is_active=True)
    session.add(cat)
    await session.flush()
    session.add(CategoryTranslation(category_id=cat.id, language_code="en", name="Dairy"))

    sub = Subcategory(category_id=cat.id, slug="milk", is_active=True)
    session.add(sub)
    await session.flush()
    session.add(SubcategoryTranslation(subcategory_id=sub.id, language_code="en", name="Milk"))

    product = MasterProduct(
        subcategory_id=sub.id, slug="amul-gold", base_price=70.0,
        brand="Amul", unit="1L", is_active=True,
    )
    session.add(product)
    await session.flush()
    session.add(MasterProductTranslation(
        master_product_id=product.id, language_code="en",
        name="Amul Gold Milk", description="Full-cream milk.",
    ))
    session.add(MasterProductTranslation(
        master_product_id=product.id, language_code="hi",
        name="अमूल गोल्ड दूध", description="फुल क्रीम दूध",
    ))
    if with_inventory:
        session.add(StoreInventory(
            store_id=store.id, product_id=product.id,
            price=68.0, stock=12, is_available=True,
        ))
    # Capture IDs BEFORE commit so attributes don't expire afterwards.
    ids = {"store_id": store.id, "product_id": product.id, "service_id": svc.id}
    await session.commit()
    return ids


@pytest.mark.asyncio
async def test_build_product_doc_full(session: AsyncSession):
    seed = await _seed_chain(session)
    doc = await build_product_document(session, seed["product_id"])
    assert doc is not None
    assert doc["id"] == seed["product_id"]
    assert doc["name_en"] == "Amul Gold Milk"
    assert doc["name_hi"] == "अमूल गोल्ड दूध"
    assert doc["service_id"] == seed["service_id"]
    assert doc["in_stock_anywhere"] is True
    assert doc["min_price"] == 68.0
    assert len(doc["per_store_offers"]) == 1
    assert doc["per_store_offers"][0]["store_id"] == seed["store_id"]


@pytest.mark.asyncio
async def test_build_product_doc_missing_translations_fall_back_to_en(session: AsyncSession):
    seed = await _seed_chain(session, with_inventory=False)
    doc = await build_product_document(session, seed["product_id"])
    assert doc is not None
    # mr/gu/pa translations not seeded -> fall back to en
    assert doc["name_mr"] == "Amul Gold Milk"
    assert doc["name_gu"] == "Amul Gold Milk"
    assert doc["name_pa"] == "Amul Gold Milk"


@pytest.mark.asyncio
async def test_build_product_doc_no_inventory(session: AsyncSession):
    seed = await _seed_chain(session, with_inventory=False)
    doc = await build_product_document(session, seed["product_id"])
    assert doc is not None
    assert doc["store_ids"] == []
    assert doc["per_store_offers"] == []
    assert doc["in_stock_anywhere"] is False
    assert doc["min_price"] == doc["base_price"]


@pytest.mark.asyncio
async def test_build_product_doc_returns_none_for_missing(session: AsyncSession):
    doc = await build_product_document(session, 9999999)
    assert doc is None


@pytest.mark.asyncio
async def test_build_store_doc(session: AsyncSession):
    seed = await _seed_chain(session)
    doc = await build_store_document(session, seed["store_id"])
    assert doc is not None
    assert doc["id"] == seed["store_id"]
    assert doc["name"] == "Raj Kirana"
    assert seed["service_id"] in doc["service_ids"]
    assert doc["lat"] == pytest.approx(19.07)
    assert doc["lng"] == pytest.approx(72.87)


@pytest.mark.asyncio
async def test_product_doc_carries_db_updated_at(session: AsyncSession):
    from sqlalchemy import select

    seed = await _seed_chain(session)
    product = (
        await session.execute(
            select(MasterProduct).where(MasterProduct.id == seed["product_id"])
        )
    ).scalar_one()
    doc = await build_product_document(session, seed["product_id"])
    assert doc is not None
    assert "db_updated_at" in doc
    assert doc["db_updated_at"] == int(product.updated_at.timestamp())


@pytest.mark.asyncio
async def test_store_doc_carries_db_updated_at(session: AsyncSession):
    from sqlalchemy import select

    seed = await _seed_chain(session)
    store = (
        await session.execute(
            select(Store).where(Store.id == seed["store_id"])
        )
    ).scalar_one()
    doc = await build_store_document(session, seed["store_id"])
    assert doc is not None
    assert "db_updated_at" in doc
    assert doc["db_updated_at"] == int(store.updated_at.timestamp())


@pytest.mark.asyncio
async def test_build_search_term_docs(session: AsyncSession):
    await _seed_chain(session)
    docs = await build_search_term_docs(session)
    terms = {(d["term"], d["locale"]) for d in docs}
    assert ("amul gold milk", "en") in terms
    assert ("dairy", "en") in terms
    assert ("milk", "en") in terms
    assert all(d["weight"] >= 1 for d in docs)
