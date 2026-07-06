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

from app.models.catalog import Category, MasterProduct, Subcategory
from app.models.platform_fee import ArrangementStatus, FeeArrangement, FeeModel
from app.models.store import StoreInventory
from app.search.reindex import reindex_all


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
