# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import Category, MasterProduct, Subcategory
from app.models.platform_fee import ArrangementStatus, FeeArrangement, FeeModel
from app.models.store import StoreInventory


async def _stock_one_product(session, bundle):
    """Add one available inventory row under the store's service so the
    storefront tree has a service node to hide."""
    cat = Category(service_id=bundle.service_id, slug="c-hide", is_active=True, sort_order=0)
    session.add(cat)
    await session.flush()
    sub = Subcategory(category_id=cat.id, slug="s-hide", is_active=True, sort_order=0)
    session.add(sub)
    await session.flush()
    prod = MasterProduct(
        subcategory_id=sub.id, slug="p-hide", is_active=True, image_url=None, base_price=10.0
    )
    session.add(prod)
    await session.flush()
    session.add(StoreInventory(
        store_id=bundle.store.id, product_id=prod.id, price=10.0, stock=5, is_available=True,
    ))
    await session.commit()


@pytest.mark.asyncio
async def test_storefront_hides_suspended_service(
    client: AsyncClient, session: AsyncSession, approved_seller_with_store
) -> None:
    await _stock_one_product(session, approved_seller_with_store)
    # Baseline: the service appears.
    r = await client.get(f"/api/v1/stores/{approved_seller_with_store.store.id}/storefront")
    assert r.status_code == 200
    assert any(s["id"] == approved_seller_with_store.service_id for s in r.json()["services"])
    # Suspend that (store, service): it disappears from the storefront tree.
    session.add(FeeArrangement(
        store_id=approved_seller_with_store.store.id,
        service_id=approved_seller_with_store.service_id,
        model=FeeModel.Subscription, status=ArrangementStatus.Suspended,
        valid_until=date(2026, 12, 1),
    ))
    await session.commit()
    r2 = await client.get(f"/api/v1/stores/{approved_seller_with_store.store.id}/storefront")
    assert r2.status_code == 200
    assert all(s["id"] != approved_seller_with_store.service_id for s in r2.json()["services"])
