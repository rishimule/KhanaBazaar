# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
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
from app.models.commerce import Cart, CartItem, Delivery
from app.models.profile import (
    CustomerAddress,
    CustomerProfile,
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from tests._helpers import make_address

mock_customer = User(id=751, email="pr-cust@kb.com", role=UserRole.Customer, is_active=True)
mock_seller = User(id=752, email="pr-seller@kb.com", role=UserRole.Seller, is_active=True)
mock_admin = User(id=753, email="pr-admin@kb.com", role=UserRole.Admin, is_active=True)


@pytest.fixture(autouse=True)
async def patch_email_dispatch() -> AsyncGenerator[None, None]:
    with (
        patch("app.api.orders.dispatch_order_placed"),
        patch("app.api.orders.dispatch_order_status_changed"),
        patch("app.api.orders.dispatch_delivery_otp"),
        patch("app.api.orders.dispatch_admin_order_action"),
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
        user_id=mock_seller.id, first_name="S", phone="+919811000752",
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
        seller_profile_id=seller.id, service_id=grocery.id, pickup_enabled=True,
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
    session.add(CartItem(cart_id=cart.id, inventory_id=inv.id, quantity=1))

    cust_address_id = (await session.exec(
        select(CustomerAddress.id).where(CustomerAddress.customer_profile_id == customer.id)
    )).first()
    ids = {
        "customer_address_id": cust_address_id,
        "store_id": store.id, "service_id": grocery.id,
        "seller_id": seller.id, "sps_id": sps.id,
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
def staff_client_factory():  # noqa: ANN201
    @asynccontextmanager
    async def _make(user: User):  # noqa: ANN202
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    return _make


async def test_order_read_exposes_delivery_mode(
    client: AsyncClient, seed: dict[str, int],
) -> None:
    resp = await client.post("/api/v1/orders", json={
        "store_id": seed["store_id"], "service_id": seed["service_id"],
        "payment_method": "upi", "delivery_mode": "pickup",
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["delivery_mode"] == "pickup"


async def test_pay_at_store_paid_on_collection(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int], staff_client_factory,
) -> None:
    place = await client.post("/api/v1/orders", json={
        "store_id": seed["store_id"], "service_id": seed["service_id"],
        "payment_method": "pay_at_store", "delivery_mode": "pickup",
    })
    assert place.status_code == 201, place.text
    oid = place.json()["id"]
    async with staff_client_factory(mock_seller) as ac:
        await ac.post(f"/api/v1/orders/{oid}/transition", json={"to": "packed"})
        await ac.post(f"/api/v1/orders/{oid}/transition", json={"to": "dispatched"})
    otp = (await session.exec(
        select(Delivery.delivery_otp).where(Delivery.order_id == oid)
    )).first()
    assert otp is not None
    async with staff_client_factory(mock_seller) as ac:
        done = await ac.post(
            f"/api/v1/orders/{oid}/transition", json={"to": "delivered", "otp": otp}
        )
    assert done.status_code == 200, done.text
    assert done.json()["payment"]["status"] == "paid"


async def test_override_address_blocked_for_pickup(
    client: AsyncClient, seed: dict[str, int], staff_client_factory,
) -> None:
    place = await client.post("/api/v1/orders", json={
        "store_id": seed["store_id"], "service_id": seed["service_id"],
        "payment_method": "upi", "delivery_mode": "pickup",
    })
    oid = place.json()["id"]
    async with staff_client_factory(mock_admin) as ac:
        resp = await ac.patch(
            f"/api/v1/admin/orders/{oid}/delivery-address",
            json={"address": make_address(pincode="560399"), "reason": "pickup order has no address"},
        )
    assert resp.status_code == 409
    assert resp.json()["detail"]["detail"] == "not_applicable_for_pickup"
