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

mock_customer = User(id=741, email="pu-cust@kb.com", role=UserRole.Customer, is_active=True)
mock_seller = User(id=742, email="pu-seller@kb.com", role=UserRole.Seller, is_active=True)
mock_admin = User(id=743, email="pu-admin@kb.com", role=UserRole.Admin, is_active=True)


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
        user_id=mock_seller.id, first_name="S", phone="+919811000742",
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
    sps = SellerProfileService(seller_profile_id=seller.id, service_id=grocery.id)
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


async def _enable_pickup(session: AsyncSession, sps_id: int, enabled: bool = True) -> None:
    sps = await session.get(SellerProfileService, sps_id)
    assert sps is not None
    sps.pickup_enabled = enabled
    await session.commit()


async def test_pickup_order_skips_address_and_fee(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int],
) -> None:
    await _enable_pickup(session, seed["sps_id"])
    resp = await client.post("/api/v1/orders", json={
        "store_id": seed["store_id"], "service_id": seed["service_id"],
        "payment_method": "pay_at_store", "delivery_mode": "pickup",
    })
    assert resp.status_code == 201, resp.text
    o = resp.json()
    assert o["delivery_mode"] == "pickup"
    assert o["delivery_fee"] == 0.0
    assert o["payment"]["method"] == "pay_at_store"
    assert o["payment"]["status"] == "pending"


async def test_pickup_requires_enabled_service(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int],
) -> None:
    # pickup_enabled defaults False
    resp = await client.post("/api/v1/orders", json={
        "store_id": seed["store_id"], "service_id": seed["service_id"],
        "payment_method": "pay_at_store", "delivery_mode": "pickup",
    })
    assert resp.status_code == 409
    assert resp.json()["detail"]["detail"] == "pickup_unavailable"


async def test_pay_at_store_rejected_for_door(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int],
) -> None:
    resp = await client.post("/api/v1/orders", json={
        "customer_address_id": seed["customer_address_id"],
        "store_id": seed["store_id"], "service_id": seed["service_id"],
        "payment_method": "pay_at_store", "delivery_mode": "door_delivery",
    })
    assert resp.status_code == 422
    assert resp.json()["detail"] == "payment_method_not_allowed"


async def test_cash_rejected_for_pickup(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int],
) -> None:
    await _enable_pickup(session, seed["sps_id"])
    resp = await client.post("/api/v1/orders", json={
        "store_id": seed["store_id"], "service_id": seed["service_id"],
        "payment_method": "cash", "delivery_mode": "pickup",
    })
    assert resp.status_code == 422
    assert resp.json()["detail"] == "payment_method_not_allowed"


async def test_net_banking_door_ok(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int],
) -> None:
    resp = await client.post("/api/v1/orders", json={
        "customer_address_id": seed["customer_address_id"],
        "store_id": seed["store_id"], "service_id": seed["service_id"],
        "payment_method": "net_banking", "delivery_mode": "door_delivery",
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["payment"]["method"] == "net_banking"


async def test_door_requires_address(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int],
) -> None:
    resp = await client.post("/api/v1/orders", json={
        "store_id": seed["store_id"], "service_id": seed["service_id"],
        "payment_method": "upi", "delivery_mode": "door_delivery",
    })
    assert resp.status_code == 422
    assert resp.json()["detail"] == "address_required"


async def test_pickup_snapshot_is_store_address(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int],
) -> None:
    await _enable_pickup(session, seed["sps_id"])
    resp = await client.post("/api/v1/orders", json={
        "store_id": seed["store_id"], "service_id": seed["service_id"],
        "payment_method": "upi", "delivery_mode": "pickup",
    })
    assert resp.status_code == 201, resp.text
    # store address pincode 560302 appears in the snapshot (pickup location).
    assert "560302" in resp.json()["delivery_address_snapshot"]
