# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Integration tests for the seller delivery-ETA window: direct/admin edits,
the change-request partial-update semantics, cart read, and the checkout
snapshot (including immutability after a later seller edit)."""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_user
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
from app.models.commerce import Cart, CartItem
from app.models.profile import (
    CustomerAddress,
    CustomerProfile,
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from tests._helpers import make_address

mock_customer = User(id=711, email="eta-cust@kb.com", role=UserRole.Customer, is_active=True)
mock_seller = User(id=712, email="eta-seller@kb.com", role=UserRole.Seller, is_active=True)
mock_admin = User(id=713, email="eta-admin@kb.com", role=UserRole.Admin, is_active=True)


@pytest.fixture(autouse=True)
async def patch_email_dispatch() -> AsyncGenerator[None, None]:
    with (
        patch("app.api.orders.dispatch_order_placed"),
        patch("app.api.orders.dispatch_order_status_changed"),
    ):
        yield


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[dict[str, int], None]:
    for u in (mock_customer, mock_seller, mock_admin):
        session.add(User(**u.model_dump()))
    await session.flush()

    customer = CustomerProfile(user_id=mock_customer.id, first_name="C")
    session.add(customer)
    await session.flush()

    cust_addr = Address(**make_address(pincode="560300", latitude=12.9716, longitude=77.5946))
    session.add(cust_addr)
    await session.flush()
    session.add(CustomerAddress(
        customer_profile_id=customer.id, address_id=cust_addr.id, is_default=True,
    ))

    seller_addr = Address(**make_address(pincode="560301", latitude=12.9716, longitude=77.5946))
    session.add(seller_addr)
    await session.flush()
    seller = SellerProfile(
        user_id=mock_seller.id, first_name="S", phone="+919811000712",
        business_name="Shop", bank_account_number="2", bank_ifsc="HDFC0000002",
        verification_status=VerificationStatus.Approved,
        business_address_id=seller_addr.id,
    )
    session.add(seller)
    await session.flush()

    store_addr = Address(**make_address(pincode="560302", latitude=12.9716, longitude=77.5946))
    session.add(store_addr)
    await session.flush()
    store = Store(name="Shop", seller_profile_id=seller.id, address_id=store_addr.id)
    session.add(store)
    await session.flush()

    grocery = Service(slug="grocery")
    session.add(grocery)
    await session.flush()
    session.add(ServiceTranslation(service_id=grocery.id, language_code="en", name="Grocery"))
    sps = SellerProfileService(
        seller_profile_id=seller.id, service_id=grocery.id,
        delivery_eta_min_minutes=25, delivery_eta_max_minutes=40,
    )
    session.add(sps)
    await session.flush()

    category = Category(service_id=grocery.id, slug="g-cat")
    session.add(category)
    await session.flush()
    session.add(CategoryTranslation(category_id=category.id, language_code="en", name="g-cat"))
    subcat = Subcategory(category_id=category.id, slug="g-sub")
    session.add(subcat)
    await session.flush()
    session.add(SubcategoryTranslation(subcategory_id=subcat.id, language_code="en", name="g-sub"))
    product = MasterProduct(subcategory_id=subcat.id, slug="rice", base_price=50.0)
    session.add(product)
    await session.flush()
    session.add(MasterProductTranslation(
        master_product_id=product.id, language_code="en", name="Rice", description="Rice",
    ))
    await session.flush()
    inv = StoreInventory(
        store_id=store.id, product_id=product.id, price=50.0, stock=10, is_available=True,
    )
    session.add(inv)
    await session.flush()

    cart = Cart(customer_profile_id=customer.id, store_id=store.id, service_id=grocery.id)
    session.add(cart)
    await session.flush()
    session.add(CartItem(cart_id=cart.id, inventory_id=inv.id, quantity=1))  # subtotal = 50

    cust_address_id = (await session.exec(
        select(CustomerAddress.id).where(CustomerAddress.customer_profile_id == customer.id)
    )).first()
    assert cust_address_id is not None
    ids = {
        "customer_address_id": cust_address_id,
        "store_id": store.id,
        "service_id": grocery.id,
        "seller_id": seller.id,
        "sps_id": sps.id,
    }
    await session.commit()
    yield ids  # type: ignore[misc]


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_current_user] = lambda: mock_customer
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def seller_client_factory():  # noqa: ANN201
    @asynccontextmanager
    async def _make(user: User):  # noqa: ANN202
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    return _make


async def _make_pending(session: AsyncSession, seller_id: int) -> None:
    seller = (await session.exec(
        select(SellerProfile).where(SellerProfile.id == seller_id)
    )).first()
    assert seller is not None
    seller.verification_status = VerificationStatus.Pending
    await session.commit()


# --- direct (pending seller) edits ---------------------------------------

async def test_direct_edit_sets_eta(
    seller_client_factory, session: AsyncSession, seed: dict[str, int],
) -> None:
    await _make_pending(session, seed["seller_id"])
    async with seller_client_factory(mock_seller) as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/me/services/{seed['service_id']}",
            json={
                "min_order_value": 100,
                "delivery_eta_min_minutes": 30,
                "delivery_eta_max_minutes": 45,
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["delivery_eta_min_minutes"] == 30
    assert body["delivery_eta_max_minutes"] == 45


async def test_direct_edit_rejects_min_gt_max(
    seller_client_factory, session: AsyncSession, seed: dict[str, int],
) -> None:
    await _make_pending(session, seed["seller_id"])
    async with seller_client_factory(mock_seller) as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/me/services/{seed['service_id']}",
            json={
                "min_order_value": 0,
                "delivery_eta_min_minutes": 90,
                "delivery_eta_max_minutes": 30,
            },
        )
    assert resp.status_code == 422


async def test_direct_edit_rejects_over_cap(
    seller_client_factory, session: AsyncSession, seed: dict[str, int],
) -> None:
    await _make_pending(session, seed["seller_id"])
    async with seller_client_factory(mock_seller) as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/me/services/{seed['service_id']}",
            json={
                "min_order_value": 0,
                "delivery_eta_min_minutes": 1,
                "delivery_eta_max_minutes": 20161,
            },
        )
    assert resp.status_code == 422


async def test_direct_edit_min_only_preserves_eta(
    seller_client_factory, session: AsyncSession, seed: dict[str, int],
) -> None:
    # Backward-compatible partial update: a min-order-only PATCH must NOT
    # clobber the existing ETA window (seeded 25/40).
    await _make_pending(session, seed["seller_id"])
    async with seller_client_factory(mock_seller) as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/me/services/{seed['service_id']}",
            json={"min_order_value": 75},
        )
    assert resp.status_code == 200, resp.text
    sps = await session.get(SellerProfileService, seed["sps_id"])
    await session.refresh(sps)
    assert sps.min_order_value == 75
    assert sps.delivery_eta_min_minutes == 25
    assert sps.delivery_eta_max_minutes == 40


# --- admin edits ----------------------------------------------------------

async def test_admin_edit_sets_eta_and_audits(
    seller_client_factory, session: AsyncSession, seed: dict[str, int],
) -> None:
    async with seller_client_factory(mock_admin) as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/admin/{mock_seller.id}/services/{seed['service_id']}",
            json={
                "min_order_value": 50,
                "delivery_eta_min_minutes": 60,
                "delivery_eta_max_minutes": 120,
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["delivery_eta_min_minutes"] == 60
    assert body["delivery_eta_max_minutes"] == 120
    from app.models.admin_audit import AdminActionLog
    logs = (await session.exec(select(AdminActionLog))).all()
    assert any(row.action == "service.set_min_order_value" for row in logs)


# --- cart read ------------------------------------------------------------

async def test_cart_read_includes_eta(
    client: AsyncClient, seed: dict[str, int],
) -> None:
    resp = await client.get("/api/v1/carts")
    assert resp.status_code == 200, resp.text
    carts = resp.json()["carts"]
    assert len(carts) == 1
    assert carts[0]["delivery_eta_min_minutes"] == 25
    assert carts[0]["delivery_eta_max_minutes"] == 40


# --- change-request flow --------------------------------------------------

async def test_change_request_applies_eta(
    session: AsyncSession, seed: dict[str, int],
) -> None:
    from app.models.seller_profile_change_request import SellerProfileChangeGroup
    from app.services.seller_profile_change_requests import (
        approve,
        create_change_request,
    )

    profile = (await session.exec(
        select(SellerProfile).where(SellerProfile.id == seed["seller_id"])
    )).first()
    assert profile is not None

    created = await create_change_request(
        session=session, seller_profile=profile,
        group=SellerProfileChangeGroup.Services,
        proposed={"services": [{
            "service_id": seed["service_id"],
            "min_order_value": 0.0,
            "delivery_eta_min_minutes": 50,
            "delivery_eta_max_minutes": 80,
        }]},
        note=None, actor_user_id=mock_seller.id,
    )
    await session.commit()
    await approve(session=session, cr=created.cr, admin_user_id=mock_admin.id)
    await session.commit()

    sps = await session.get(SellerProfileService, seed["sps_id"])
    await session.refresh(sps)
    assert sps.delivery_eta_min_minutes == 50
    assert sps.delivery_eta_max_minutes == 80


# --- checkout snapshot ----------------------------------------------------

async def test_checkout_snapshots_eta_immutably(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int],
) -> None:
    resp = await client.post("/api/v1/orders", json={
        "customer_address_id": seed["customer_address_id"],
        "store_id": seed["store_id"],
        "service_id": seed["service_id"],
        "payment_method": "upi",
    })
    assert resp.status_code == 201, resp.text
    order = resp.json()
    assert order["delivery_eta_min_minutes"] == 25
    assert order["delivery_eta_max_minutes"] == 40

    # A later seller edit must NOT mutate the placed order's snapshot.
    sps = await session.get(SellerProfileService, seed["sps_id"])
    sps.delivery_eta_min_minutes = 99
    sps.delivery_eta_max_minutes = 199
    await session.commit()

    detail = await client.get(f"/api/v1/orders/{order['id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["delivery_eta_min_minutes"] == 25
    assert detail.json()["delivery_eta_max_minutes"] == 40
