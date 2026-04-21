from typing import Any, AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_admin, get_current_seller, get_current_user
from app.models.base import User, UserRole

# Mock Users for dependency overrides
mock_admin = User(id=1, email="admin@kb.com", full_name="Admin", role=UserRole.Admin, is_active=True)
mock_seller = User(id=2, email="seller@kb.com", full_name="Seller", role=UserRole.Seller, is_active=True)
mock_customer = User(id=3, email="cust@kb.com", full_name="Customer", role=UserRole.Customer, is_active=True)


@pytest.fixture(autouse=True)
async def seed_mock_users(session: AsyncSession) -> AsyncGenerator[None, None]:
    session.add(User(**mock_admin.model_dump()))
    session.add(User(**mock_seller.model_dump()))
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
        # Create Category
        cat_data = {"name": "Dairy", "description": "Milk products"}
        cat_resp = await ac.post("/api/v1/catalog/categories", json=cat_data)
        assert cat_resp.status_code == 200
        category = cat_resp.json()
        assert category["name"] == "Dairy"

        # Create Product
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

@pytest.mark.asyncio
async def test_seller_can_create_store(override_as_seller: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Create Store
        store_data = {"name": "Rishi's Supermarket", "address": "123 Main St"}
        store_resp = await ac.post("/api/v1/stores/", json=store_data)
        assert store_resp.status_code == 200
        store = store_resp.json()
        assert store["name"] == "Rishi's Supermarket"
        assert store["seller_id"] == mock_seller.id

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
