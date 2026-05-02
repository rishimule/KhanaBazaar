from collections.abc import AsyncGenerator, Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
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
from app.models.profile import CustomerProfile, SellerProfile, VerificationStatus
from app.models.store import Store, StoreInventory
from tests._helpers import make_address

mock_customer = User(id=201, email="cart-customer@kb.com", role=UserRole.Customer, is_active=True)
mock_other_customer = User(id=202, email="cart-other@kb.com", role=UserRole.Customer, is_active=True)
mock_seller = User(id=203, email="cart-seller@kb.com", role=UserRole.Seller, is_active=True)


async def _seed_product(
    session: AsyncSession, *, service_slug: str, category_slug: str,
    subcategory_slug: str, product_slug: str, name: str, base_price: float,
) -> MasterProduct:
    """Create the full Service → Category → Subcategory → MasterProduct chain
    plus English translations. Each slug must be globally unique within its scope.
    The 'en' Language row is seeded by the autouse `setup_test_db` fixture in
    `conftest.py`."""
    service = Service(slug=service_slug)
    session.add(service)
    await session.flush()
    session.add(ServiceTranslation(service_id=service.id, language_code="en", name=name))

    category = Category(service_id=service.id, slug=category_slug)
    session.add(category)
    await session.flush()
    session.add(CategoryTranslation(category_id=category.id, language_code="en", name=name))

    subcat = Subcategory(category_id=category.id, slug=subcategory_slug)
    session.add(subcat)
    await session.flush()
    session.add(SubcategoryTranslation(subcategory_id=subcat.id, language_code="en", name=name))

    product = MasterProduct(subcategory_id=subcat.id, slug=product_slug, base_price=base_price)
    session.add(product)
    await session.flush()
    session.add(MasterProductTranslation(
        master_product_id=product.id, language_code="en", name=name, description=name,
    ))
    await session.flush()
    return product


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[None, None]:
    for u in (mock_customer, mock_other_customer, mock_seller):
        session.add(User(**u.model_dump()))
    await session.flush()

    customer_profile = CustomerProfile(user_id=mock_customer.id, first_name="Cust")
    other_profile = CustomerProfile(user_id=mock_other_customer.id, first_name="Other")
    session.add_all([customer_profile, other_profile])
    await session.flush()

    seller_addr = Address(**make_address(pincode="560001"))
    session.add(seller_addr)
    await session.flush()
    seller_profile = SellerProfile(
        user_id=mock_seller.id, first_name="Sel", phone="+919800000001",
        business_name="S", business_category="grocery",
        bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=seller_addr.id,
    )
    session.add(seller_profile)
    await session.flush()

    store_addr = Address(**make_address(pincode="560002"))
    session.add(store_addr)
    await session.flush()
    store = Store(name="Test Store", seller_profile_id=seller_profile.id, address_id=store_addr.id)
    session.add(store)
    await session.flush()

    product = await _seed_product(
        session, service_slug="grocery", category_slug="food",
        subcategory_slug="fruit", product_slug="apple", name="Apple", base_price=50.0,
    )

    inv = StoreInventory(store_id=store.id, product_id=product.id, price=50.0, stock=10)
    session.add(inv)
    await session.flush()

    # Pre-existing cart row for the main customer for read tests.
    cart = Cart(customer_profile_id=customer_profile.id, store_id=store.id)
    session.add(cart)
    await session.flush()
    session.add(CartItem(cart_id=cart.id, inventory_id=inv.id, quantity=2))
    await session.commit()
    yield


@pytest.fixture
def override_as_customer() -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: mock_customer
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def override_as_other_customer() -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: mock_other_customer
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def override_as_seller() -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    yield
    app.dependency_overrides.pop(get_current_user, None)


async def test_guest_cannot_list_carts() -> None:
    app.dependency_overrides.pop(get_current_user, None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/carts")
    assert resp.status_code == 401


async def test_seller_cannot_list_carts(override_as_seller: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/carts")
    assert resp.status_code == 403


async def test_customer_lists_their_carts(override_as_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/carts")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["carts"]) == 1
    cart = data["carts"][0]
    assert cart["store_name"] == "Test Store"
    assert cart["subtotal"] == 100.0
    assert cart["items"][0]["product_name"] == "Apple"
    assert cart["items"][0]["quantity"] == 2


async def test_other_customer_sees_empty_list(override_as_other_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/carts")
    assert resp.status_code == 200
    assert resp.json() == {"carts": []}
