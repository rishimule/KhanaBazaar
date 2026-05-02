from collections.abc import AsyncGenerator, Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.commerce import (
    Cart,
    CartItem,
    Delivery,
    Order,
    OrderItem,
    Payment,
    PaymentStatus,
)
from app.models.profile import (
    CustomerAddress,
    CustomerProfile,
    SellerProfile,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from tests._helpers import make_address

mock_customer = User(id=301, email="ord-cust@kb.com", role=UserRole.Customer, is_active=True)
mock_other_customer = User(id=302, email="ord-other@kb.com", role=UserRole.Customer, is_active=True)
mock_seller = User(id=303, email="ord-seller@kb.com", role=UserRole.Seller, is_active=True)
mock_other_seller = User(id=304, email="ord-other-seller@kb.com", role=UserRole.Seller, is_active=True)
mock_admin = User(id=305, email="ord-admin@kb.com", role=UserRole.Admin, is_active=True)


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[dict[str, int], None]:
    """Seed two customers, two sellers each with a store, two inventory rows, addresses, plus a cart for the main customer."""
    for u in (mock_customer, mock_other_customer, mock_seller, mock_other_seller, mock_admin):
        session.add(User(**u.model_dump()))
    await session.flush()

    customer_profile = CustomerProfile(user_id=mock_customer.id, first_name="Cust")
    other_customer_profile = CustomerProfile(user_id=mock_other_customer.id, first_name="Other")
    session.add_all([customer_profile, other_customer_profile])
    await session.flush()

    cust_addr = Address(**make_address(pincode="560050"))
    session.add(cust_addr)
    await session.flush()
    cust_address = CustomerAddress(
        customer_profile_id=customer_profile.id, address_id=cust_addr.id, is_default=True,
    )
    session.add(cust_address)

    seller_business_addr = Address(**make_address(pincode="560100"))
    session.add(seller_business_addr)
    await session.flush()
    seller_profile = SellerProfile(
        user_id=mock_seller.id, first_name="S1", phone="+919800000010",
        business_name="S1 Store", business_category="grocery",
        bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=seller_business_addr.id,
    )
    session.add(seller_profile)

    other_seller_business_addr = Address(**make_address(pincode="560101"))
    session.add(other_seller_business_addr)
    await session.flush()
    other_seller_profile = SellerProfile(
        user_id=mock_other_seller.id, first_name="S2", phone="+919800000020",
        business_name="S2 Store", business_category="grocery",
        bank_account_number="2", bank_ifsc="HDFC0000002",
        verification_status=VerificationStatus.Approved,
        business_address_id=other_seller_business_addr.id,
    )
    session.add(other_seller_profile)
    await session.flush()

    store_addr = Address(**make_address(pincode="560110"))
    other_store_addr = Address(**make_address(pincode="560111"))
    session.add_all([store_addr, other_store_addr])
    await session.flush()

    store_a = Store(name="Store A", seller_profile_id=seller_profile.id, address_id=store_addr.id)
    store_b = Store(name="Store B", seller_profile_id=other_seller_profile.id, address_id=other_store_addr.id)
    session.add_all([store_a, store_b])
    await session.flush()

    # Reuse the seeding helper from test_carts.py.
    from tests.test_carts import _seed_product

    product = await _seed_product(
        session, service_slug="grocery", category_slug="food",
        subcategory_slug="fruit", product_slug="apple", name="Apple", base_price=50.0,
    )
    product_b = await _seed_product(
        session, service_slug="bakery", category_slug="bread-cat",
        subcategory_slug="loaves", product_slug="bread", name="Bread", base_price=30.0,
    )

    inv_a = StoreInventory(store_id=store_a.id, product_id=product.id, price=50.0, stock=10)
    inv_b = StoreInventory(store_id=store_b.id, product_id=product_b.id, price=30.0, stock=4)
    session.add_all([inv_a, inv_b])
    await session.flush()

    # Multi-store cart for main customer.
    cart_a = Cart(customer_profile_id=customer_profile.id, store_id=store_a.id)
    cart_b = Cart(customer_profile_id=customer_profile.id, store_id=store_b.id)
    session.add_all([cart_a, cart_b])
    await session.flush()
    session.add_all([
        CartItem(cart_id=cart_a.id, inventory_id=inv_a.id, quantity=2),
        CartItem(cart_id=cart_b.id, inventory_id=inv_b.id, quantity=1),
    ])

    # Capture IDs before commit; commit expires attributes which would trigger
    # lazy reloads in async context (MissingGreenlet).
    ids = {
        "customer_address_id": cust_address.id,
        "store_a": store_a.id,
        "store_b": store_b.id,
        "inv_a": inv_a.id,
        "inv_b": inv_b.id,
        "customer_profile": customer_profile.id,
        "seller_profile": seller_profile.id,
    }
    await session.commit()

    yield ids


def _override(user: User) -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: user
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def as_customer() -> Iterator[None]:
    yield from _override(mock_customer)


@pytest.fixture
def as_other_customer() -> Iterator[None]:
    yield from _override(mock_other_customer)


@pytest.fixture
def as_seller() -> Iterator[None]:
    yield from _override(mock_seller)


@pytest.fixture
def as_other_seller() -> Iterator[None]:
    yield from _override(mock_other_seller)


@pytest.fixture
def as_admin() -> Iterator[None]:
    yield from _override(mock_admin)


async def test_place_orders_fans_out_per_store(as_customer: Any, seed: dict[str, int], session: AsyncSession) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/orders", json={"customer_address_id": seed["customer_address_id"]})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["orders"]) == 2
    totals = sorted(o["total"] for o in body["orders"])
    assert totals == [30.0, 100.0]

    orders = (await session.exec(select(Order))).all()
    assert len(orders) == 2
    payments = (await session.exec(select(Payment))).all()
    assert len(payments) == 2
    assert all(p.status == PaymentStatus.Pending for p in payments)
    deliveries = (await session.exec(select(Delivery))).all()
    assert len(deliveries) == 2
    items = (await session.exec(select(OrderItem))).all()
    assert {i.product_name_snapshot for i in items} == {"Apple", "Bread"}

    inv_a = (await session.exec(select(StoreInventory).where(StoreInventory.id == seed["inv_a"]))).first()
    inv_b = (await session.exec(select(StoreInventory).where(StoreInventory.id == seed["inv_b"]))).first()
    assert inv_a.stock == 8
    assert inv_b.stock == 3

    remaining_carts = (await session.exec(select(Cart))).all()
    assert remaining_carts == []


async def test_place_orders_empty_cart(as_other_customer: Any, seed: dict[str, int]) -> None:
    # other_customer has a CustomerProfile but no Cart rows; the address belongs
    # to the main customer so the 403 path doesn't fire — we expect cart_empty.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/orders", json={"customer_address_id": seed["customer_address_id"]})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "invalid_address"


async def test_place_orders_invalid_address(as_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/orders", json={"customer_address_id": 9999})
    assert resp.status_code == 404


async def test_place_orders_insufficient_stock(as_customer: Any, seed: dict[str, int], session: AsyncSession) -> None:
    inv = (await session.exec(select(StoreInventory).where(StoreInventory.id == seed["inv_a"]))).first()
    inv.stock = 1   # cart wants 2
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/orders", json={"customer_address_id": seed["customer_address_id"]})
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["detail"] == "insufficient_stock"
    # Both stocks unchanged on rollback.
    inv = (await session.exec(select(StoreInventory).where(StoreInventory.id == seed["inv_a"]))).first()
    inv_b = (await session.exec(select(StoreInventory).where(StoreInventory.id == seed["inv_b"]))).first()
    assert inv.stock == 1 and inv_b.stock == 4
    # Full rollback: no orders / payments / deliveries / order_items, cart still intact.
    assert (await session.exec(select(Order))).all() == []
    assert (await session.exec(select(Payment))).all() == []
    assert (await session.exec(select(Delivery))).all() == []
    assert (await session.exec(select(OrderItem))).all() == []
    remaining_carts = (await session.exec(select(Cart))).all()
    assert len(remaining_carts) == 2  # cart_a + cart_b still present
    remaining_items = (await session.exec(select(CartItem))).all()
    assert len(remaining_items) == 2  # both cart items still present
