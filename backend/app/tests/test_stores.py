from typing import Any, AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_admin, get_current_seller, get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.profile import SellerProfile, VerificationStatus
from tests._helpers import make_address

mock_admin = User(id=1, email="admin@kb.com", role=UserRole.Admin, is_active=True)
mock_seller = User(id=2, email="seller@kb.com", role=UserRole.Seller, is_active=True)
mock_customer = User(id=3, email="cust@kb.com", role=UserRole.Customer, is_active=True)


@pytest.fixture(autouse=True)
async def seed_mock_users(session: AsyncSession) -> AsyncGenerator[None, None]:
    session.add(User(**mock_admin.model_dump()))
    session.add(User(**mock_seller.model_dump()))
    await session.flush()
    address = Address(**make_address())
    session.add(address)
    await session.flush()
    session.add(SellerProfile(
        user_id=mock_seller.id,
        first_name="Seller",
        last_name=None,
        business_name="Seller Store",
        business_category="grocery",
        phone="+919811110000",
        gst_number="06AAAAA1111A1Z1",
        fssai_license="44556677889900",
        bank_account_number="80100200300700",
        bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=address.id,
    ))
    await session.commit()
    yield


@pytest.fixture
def override_as_admin() -> Iterator[None]:
    app.dependency_overrides[get_current_admin] = lambda: mock_admin
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    yield None
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def override_as_seller() -> Iterator[None]:
    app.dependency_overrides[get_current_seller] = lambda: mock_seller
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    yield None
    app.dependency_overrides.pop(get_current_seller, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_can_create_category_and_product(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        cat_data = {"name": "Dairy", "description": "Milk products"}
        cat_resp = await ac.post("/api/v1/catalog/categories", json=cat_data)
        assert cat_resp.status_code == 200
        category = cat_resp.json()
        assert category["name"] == "Dairy"

        prod_data = {
            "name": "Amul Butter 100g",
            "description": "Delicious butter",
            "base_price": 55.0,
            "category_id": category["id"]
        }
        prod_resp = await ac.post("/api/v1/catalog/products", json=prod_data)
        assert prod_resp.status_code == 200
        product = prod_resp.json()
        assert product["name"] == "Amul Butter 100g"
        assert product["category_id"] == category["id"]


@pytest.mark.asyncio
async def test_seller_can_create_store(override_as_seller: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        store_data = {"name": "Rishi's Supermarket", "address": make_address()}
        store_resp = await ac.post("/api/v1/stores/", json=store_data)
        assert store_resp.status_code == 200
        store = store_resp.json()
        assert store["name"] == "Rishi's Supermarket"
        assert store["seller_id"] == mock_seller.id
        assert store["address"] == store_data["address"]


@pytest.mark.asyncio
async def test_create_store_rejects_missing_address_line1(override_as_seller: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        store_data = {"name": "Mini Mart", "address": make_address(address_line1="")}
        resp = await ac.post("/api/v1/stores/", json=store_data)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_store_by_id_returns_nested_address(override_as_seller: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        store_data = {"name": "Mini Mart", "address": make_address()}
        create_resp = await ac.post("/api/v1/stores/", json=store_data)
        store_id = create_resp.json()["id"]
        get_resp = await ac.get(f"/api/v1/stores/{store_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["address"] == store_data["address"]


@pytest.mark.asyncio
async def test_public_can_fetch_products_and_stores() -> None:
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_current_seller, None)
    app.dependency_overrides.pop(get_current_user, None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        prod_resp = await ac.get("/api/v1/catalog/products")
        assert prod_resp.status_code == 200

        stores_resp = await ac.get("/api/v1/stores/")
        assert stores_resp.status_code == 200
