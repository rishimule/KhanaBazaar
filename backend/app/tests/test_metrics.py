# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
"""Smoke tests for dashboard metrics endpoints (admin + seller).

Covers day/month window boundaries (an old order outside the windows must NOT
be counted) and the full metric shape on both routes.
"""
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import (
    get_current_admin,
    get_current_seller,
    get_current_user,
)
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import Service, ServiceTranslation
from app.models.commerce import (
    Delivery,
    DeliveryStatus,
    Order,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from app.models.profile import (
    CustomerProfile,
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from tests._helpers import make_address

admin_user = User(id=701, email="metrics-admin@kb.com", role=UserRole.Admin, is_active=True)
seller_user = User(id=702, email="metrics-seller@kb.com", role=UserRole.Seller, is_active=True)
customer_user = User(id=703, email="metrics-cust@kb.com", role=UserRole.Customer, is_active=True)


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[dict[str, int], None]:
    from tests.test_carts import _seed_product

    for u in (admin_user, seller_user, customer_user):
        session.add(User(**u.model_dump()))
    await session.flush()

    cust = CustomerProfile(user_id=customer_user.id, first_name="C")
    seller_biz_addr = Address(**make_address())
    session.add(seller_biz_addr)
    await session.flush()
    seller = SellerProfile(
        user_id=seller_user.id,
        first_name="S",
        last_name="P",
        business_name="MetricsCo",
        phone="+910000000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=seller_biz_addr.id,
    )
    session.add_all([cust, seller])
    await session.flush()

    product, svc_id = await _seed_product(
        session,
        service_slug="metrics-svc",
        category_slug="metrics-cat",
        subcategory_slug="metrics-sub",
        product_slug="metrics-prod",
        name="MetricProd",
        base_price=10.0,
    )
    product_2, _ = await _seed_product(
        session,
        service_slug="metrics-svc-2",
        category_slug="metrics-cat-2",
        subcategory_slug="metrics-sub-2",
        product_slug="metrics-prod-2",
        name="MetricProd2",
        base_price=20.0,
    )

    store_addr = Address(**make_address())
    session.add(store_addr)
    await session.flush()
    store = Store(
        name="Metrics Store",
        is_active=True,
        seller_profile_id=seller.id,
        address_id=store_addr.id,
        delivery_radius_km=5.0,
        pin_confirmed=True,
    )
    session.add(store)
    await session.flush()

    # A service the store offers but stocks zero products — must still render.
    empty_service = Service(slug="metrics-empty-svc")
    session.add(empty_service)
    await session.flush()
    session.add(ServiceTranslation(
        service_id=empty_service.id, language_code="en", name="EmptyService",
    ))
    session.add(SellerProfileService(
        seller_profile_id=seller.id, service_id=empty_service.id,
    ))
    await session.flush()

    # Inventory: 3 rows — one normal, one out-of-stock, one unavailable.
    session.add_all([
        StoreInventory(store_id=store.id, product_id=product.id, price=10.0, stock=20, is_available=True),
        StoreInventory(store_id=store.id, product_id=product_2.id, price=20.0, stock=0, is_available=True),
    ])
    # Add a third inventory row tied to yet another product to test unavailable
    product_3, _ = await _seed_product(
        session,
        service_slug="metrics-svc-3",
        category_slug="metrics-cat-3",
        subcategory_slug="metrics-sub-3",
        product_slug="metrics-prod-3",
        name="MetricProd3",
        base_price=15.0,
    )
    session.add(StoreInventory(store_id=store.id, product_id=product_3.id, price=15.0, stock=5, is_available=False))
    await session.flush()

    delivery_addr = Address(**make_address())
    session.add(delivery_addr)
    await session.flush()

    now = datetime.now(timezone.utc)
    last_month = (now.replace(day=1) - timedelta(days=2))

    # Seeded orders:
    # - 1 delivered today (delivered_at NOW)  → counts everywhere
    # - 1 pending today                       → active + today + month
    # - 1 last-month order (delivered)        → must NOT count toward today/month/revenue
    seed_specs = [
        # (status, placed_at, total, delivered_at)
        (OrderStatus.Delivered, now - timedelta(hours=2), 100.0, now - timedelta(hours=1)),
        (OrderStatus.Pending, now - timedelta(hours=1), 50.0, None),
        (OrderStatus.Delivered, last_month, 200.0, last_month + timedelta(hours=1)),
    ]
    for status, placed, total, delivered_at in seed_specs:
        order = Order(
            customer_profile_id=cust.id,
            store_id=store.id,
            service_id=svc_id,
            service_name_snapshot="Grocery",
            delivery_address_id=delivery_addr.id,
            delivery_address_snapshot="snap",
            subtotal=total,
            delivery_fee=0,
            tax=0,
            total=total,
            status=status,
            placed_at=placed,
        )
        session.add(order)
        await session.flush()
        session.add(
            Payment(
                order_id=order.id,
                method=PaymentMethod.Upi,
                status=PaymentStatus.Paid if status == OrderStatus.Delivered else PaymentStatus.Pending,
                amount=total,
            )
        )
        session.add(
            Delivery(
                order_id=order.id,
                status=DeliveryStatus.Delivered if status == OrderStatus.Delivered else DeliveryStatus.Pending,
                delivered_at=delivered_at,
            )
        )

    store_id = store.id
    await session.commit()

    yield {"store_id": store_id}


async def test_seller_metrics(client: AsyncClient, session: AsyncSession) -> None:
    app.dependency_overrides[get_current_seller] = lambda: seller_user
    app.dependency_overrides[get_current_user] = lambda: seller_user
    try:
        res = await client.get("/api/v1/sellers/me/metrics")
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["active_orders"] == 1
        assert data["orders_today"] == 2
        # The last-month order must NOT show up in `orders_this_month`.
        assert data["orders_this_month"] == 2
        # Revenue counts only orders delivered THIS month.
        assert data["revenue_this_month"] == 100.0
        assert data["total_products"] == 3
        assert data["out_of_stock"] == 1
        assert data["unavailable"] == 1
        assert data["store_active"] is True
        assert data["pin_confirmed"] is True
        # --- new dashboard aggregation fields ---
        assert data["store_name"] == "Metrics Store"
        # Last-month delivered order total was 200.0.
        assert data["revenue_last_month"] == 200.0
        # (100 this month - 200 last month) / 200 * 100 = -50.0
        assert data["revenue_trend_pct"] == -50.0
        # Lifetime status mix: 2 delivered, 1 pending, rest 0.
        assert data["order_status_counts"]["delivered"] == 2
        assert data["order_status_counts"]["pending"] == 1
        assert data["order_status_counts"]["packed"] == 0
        assert data["order_status_counts"]["dispatched"] == 0
        assert data["order_status_counts"]["cancelled"] == 0
        # 3 services, one product each. in_stock: svc1=1 (stock20/avail),
        # svc2=0 (stock0), svc3=0 (unavailable).
        ibs = {s["service_name"]: s for s in data["inventory_by_service"]}
        assert ibs["MetricProd"]["total"] == 1
        assert ibs["MetricProd"]["in_stock"] == 1
        assert ibs["MetricProd2"]["in_stock"] == 0
        assert ibs["MetricProd3"]["in_stock"] == 0
        # Enabled service with zero products still appears, at 0 / 0.
        assert ibs["EmptyService"]["total"] == 0
        assert ibs["EmptyService"]["in_stock"] == 0
        # Only the svc1 product is in stock → top subcategory is its subcat.
        assert data["top_subcategory"]["name"] == "MetricProd"
        assert data["top_subcategory"]["count"] == 1
    finally:
        app.dependency_overrides.pop(get_current_seller, None)
        app.dependency_overrides.pop(get_current_user, None)


async def test_admin_metrics(client: AsyncClient, session: AsyncSession) -> None:
    app.dependency_overrides[get_current_admin] = lambda: admin_user
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        res = await client.get("/api/v1/admin/metrics")
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["active_orders"] == 1
        assert data["orders_today"] == 2
        assert data["orders_this_month"] == 2
        # Last-month delivered order excluded from GMV-this-month.
        assert data["gmv_this_month"] == 100.0
        assert data["active_stores"] >= 1
        assert data["approved_sellers"] >= 1
        assert data["active_master_products"] >= 3
        assert data["active_categories"] >= 3
        assert data["pending_applications"] >= 0
        # --- new dashboard fields ---
        # Last-month delivered order total was 200.0.
        assert data["gmv_last_month"] == 200.0
        # (100 this month - 200 last month) / 200 * 100 = -50.0
        assert data["gmv_trend_pct"] == -50.0
        assert data["rejected_sellers"] >= 0
        # Two orders placed this month, both on the same service.
        obs = data["orders_by_service"]
        assert isinstance(obs, list)
        assert sum(s["count"] for s in obs) == 2
        assert obs[0]["service_name"] == "MetricProd"
        assert obs[0]["count"] == 2
        # Every active service is listed, even those with zero orders this
        # month (4 services seeded — 3 with products + 1 empty enabled
        # service; the three without orders show count 0).
        assert len(obs) == 4
        assert sorted(s["count"] for s in obs) == [0, 0, 0, 2]
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_current_user, None)


async def test_revenue_series_default_range(client: AsyncClient) -> None:
    app.dependency_overrides[get_current_seller] = lambda: seller_user
    app.dependency_overrides[get_current_user] = lambda: seller_user
    try:
        res = await client.get("/api/v1/sellers/me/revenue-series")
        assert res.status_code == 200, res.text
        data = res.json()
        # Default range is 14d → 14 zero-filled daily points.
        assert len(data["points"]) == 14
        assert all("date" in p and "gov" in p for p in data["points"])
        # Two orders placed today (100 + 50) → today's GOV is 150.
        assert data["points"][-1]["gov"] == 150.0
        assert data["peak"] == 150.0
        # avg = 150 / 14 days.
        assert data["avg_per_day"] == round(150.0 / 14, 2)
    finally:
        app.dependency_overrides.pop(get_current_seller, None)
        app.dependency_overrides.pop(get_current_user, None)


async def test_revenue_series_ranges(client: AsyncClient) -> None:
    app.dependency_overrides[get_current_seller] = lambda: seller_user
    app.dependency_overrides[get_current_user] = lambda: seller_user
    try:
        for token, n in (("7d", 7), ("14d", 14), ("30d", 30)):
            res = await client.get(f"/api/v1/sellers/me/revenue-series?range={token}")
            assert res.status_code == 200, res.text
            assert len(res.json()["points"]) == n
        # Invalid range token is rejected by query validation.
        bad = await client.get("/api/v1/sellers/me/revenue-series?range=99d")
        assert bad.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_seller, None)
        app.dependency_overrides.pop(get_current_user, None)


async def test_admin_gmv_series_default_range(client: AsyncClient) -> None:
    app.dependency_overrides[get_current_admin] = lambda: admin_user
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        res = await client.get("/api/v1/admin/gmv-series")
        assert res.status_code == 200, res.text
        data = res.json()
        # Default range is 14d → 14 zero-filled daily points.
        assert len(data["points"]) == 14
        assert all("date" in p and "gov" in p for p in data["points"])
        # Two orders placed today (100 + 50) → today's GOV is 150.
        assert data["points"][-1]["gov"] == 150.0
        assert data["peak"] == 150.0
        assert data["avg_per_day"] == round(150.0 / 14, 2)
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_current_user, None)


async def test_admin_gmv_series_ranges_and_validation(client: AsyncClient) -> None:
    app.dependency_overrides[get_current_admin] = lambda: admin_user
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        for token, n in (("7d", 7), ("14d", 14), ("30d", 30)):
            res = await client.get(f"/api/v1/admin/gmv-series?range={token}")
            assert res.status_code == 200, res.text
            assert len(res.json()["points"]) == n
        bad = await client.get("/api/v1/admin/gmv-series?range=99d")
        assert bad.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_current_user, None)
