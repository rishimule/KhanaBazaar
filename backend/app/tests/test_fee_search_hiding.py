# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import Category, MasterProduct, Subcategory
from app.models.platform_fee import ArrangementStatus, FeeArrangement, FeeModel
from app.models.store import StoreInventory
from app.search.reindex import reindex_all
from app.search.serialize import build_product_document, build_store_document


async def _suspend(session, store_id, service_id):
    session.add(FeeArrangement(
        store_id=store_id, service_id=service_id, model=FeeModel.Subscription,
        status=ArrangementStatus.Suspended, valid_until=date(2026, 12, 1),
    ))
    await session.flush()


async def _stock_one_product(session, bundle):
    """Add one available inventory row under the store's service so the
    product has a per-store offer to flag."""
    cat = Category(service_id=bundle.service_id, slug="c-search-hide", is_active=True, sort_order=0)
    session.add(cat)
    await session.flush()
    sub = Subcategory(category_id=cat.id, slug="s-search-hide", is_active=True, sort_order=0)
    session.add(sub)
    await session.flush()
    prod = MasterProduct(
        subcategory_id=sub.id, slug="p-search-hide", is_active=True, image_url=None, base_price=10.0
    )
    session.add(prod)
    await session.flush()
    session.add(StoreInventory(
        store_id=bundle.store.id, product_id=prod.id, price=10.0, stock=5, is_available=True,
    ))
    await session.commit()
    return prod.id, bundle.service_id


@pytest.mark.asyncio
async def test_product_offer_flagged_suspended(
    session: AsyncSession, approved_seller_with_store
) -> None:
    bundle = approved_seller_with_store
    pid, svc_id = await _stock_one_product(session, bundle)
    await _suspend(session, bundle.store.id, svc_id)
    doc = await build_product_document(session, pid)
    offer = next(o for o in doc["per_store_offers"] if o["store_id"] == bundle.store.id)
    assert offer["suspended"] is True
    # Suspended-everywhere product → not in_stock_anywhere.
    assert doc["in_stock_anywhere"] is False


@pytest.mark.asyncio
async def test_store_doc_lists_suspended_services(
    session: AsyncSession, approved_seller_with_store
) -> None:
    bundle = approved_seller_with_store
    await _suspend(session, bundle.store.id, bundle.service_id)
    doc = await build_store_document(session, bundle.store.id)
    assert bundle.service_id in doc["suspended_service_ids"]


@pytest.mark.asyncio
async def test_arrangement_change_triggers_reindex(
    session: AsyncSession, approved_seller_with_store
) -> None:
    bundle = approved_seller_with_store
    with patch("app.search.tasks.reindex_store.delay") as rs, \
         patch("app.search.tasks.reindex_products_for_store.delay") as rp:
        session.add(FeeArrangement(
            store_id=bundle.store.id, service_id=bundle.service_id,
            model=FeeModel.Subscription, status=ArrangementStatus.Suspended,
            valid_until=date(2026, 12, 1),
        ))
        await session.commit()
    rs.assert_any_call(bundle.store.id)
    rp.assert_any_call(bundle.store.id)


@pytest.mark.asyncio
async def test_search_results_exclude_suspended_offer(
    client: AsyncClient, session: AsyncSession, meili_test_client, approved_seller_with_store
) -> None:
    """A suspended (store, service) offer must not appear in
    GET /api/v1/search/products results, even though the product itself
    (offered elsewhere or previously) is still indexed."""
    bundle = approved_seller_with_store
    pid, svc_id = await _stock_one_product(session, bundle)
    await _suspend(session, bundle.store.id, svc_id)

    await reindex_all(session, meili_test_client)

    r = await client.get("/api/v1/search/products", params={"q": "p-search-hide"})
    assert r.status_code == 200, r.text
    body = r.json()
    product = next((p for p in body["products"] if p["id"] == pid), None)
    assert product is not None, body
    assert all(o["store_id"] != bundle.store.id for o in product["per_store_offers"])


@pytest.mark.asyncio
async def test_store_listing_excludes_suspended_for_service(
    client, session, approved_seller_with_store
) -> None:
    bundle = approved_seller_with_store
    # bundle's service has a slug; resolve it for the ?service= filter.
    from app.models.catalog import Service
    slug = (await session.exec(select(Service.slug).where(Service.id == bundle.service_id))).first()
    # Baseline: store lists for its service.
    r = await client.get(f"/api/v1/stores/?service={slug}")
    assert any(s["id"] == bundle.store.id for s in r.json())
    # Suspend (store, service) → excluded from the service-filtered listing.
    await _suspend(session, bundle.store.id, bundle.service_id)
    await session.commit()
    r2 = await client.get(f"/api/v1/stores/?service={slug}")
    assert all(s["id"] != bundle.store.id for s in r2.json())
