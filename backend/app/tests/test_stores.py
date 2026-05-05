from typing import Any, AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_admin, get_current_seller, get_current_user
from sqlmodel import select

from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import Service, ServiceTranslation
from app.models.profile import SellerProfile, SellerProfileService, VerificationStatus
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
    seller_profile = SellerProfile(
        user_id=mock_seller.id,
        first_name="Seller",
        last_name=None,
        business_name="Seller Store",
        phone="+919811110000",
        gst_number="06AAAAA1111A1Z1",
        fssai_license="44556677889900",
        bank_account_number="80100200300700",
        bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=address.id,
    )
    session.add(seller_profile)
    await session.flush()

    grocery_service = Service(slug="grocery")
    session.add(grocery_service)
    await session.flush()
    session.add(ServiceTranslation(service_id=grocery_service.id, language_code="en", name="Grocery"))
    session.add(SellerProfileService(seller_profile_id=seller_profile.id, service_id=grocery_service.id))
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


@pytest.mark.asyncio
async def test_store_response_includes_services(
    override_as_seller: Any,
) -> None:
    # Create the store first
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        store_data = {"name": "Services Mart", "address": make_address()}
        create_resp = await ac.post("/api/v1/stores/", json=store_data)
        assert create_resp.status_code == 200, create_resp.text
        sid = create_resp.json()["id"]
        get_resp = await ac.get(f"/api/v1/stores/{sid}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert isinstance(body["services"], list)
    assert any(s["slug"] == "grocery" for s in body["services"])


_STORE_GROCERY_TRANSLATIONS = {
    "en": "Grocery",
    "hi": "किराना",
    "mr": "किराणा",
    "gu": "કરિયાણું",
    "pa": "ਕਰਿਆਨਾ",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("lang,expected", list(_STORE_GROCERY_TRANSLATIONS.items()))
async def test_get_store_localizes_service_names(
    session: AsyncSession, override_as_seller: Any, lang: str, expected: str
) -> None:
    # Add hi/mr/gu/pa translations onto the autouse-seeded grocery service.
    grocery_row = await session.exec(select(Service).where(Service.slug == "grocery"))
    grocery = grocery_row.first()
    assert grocery is not None and grocery.id is not None
    for code, name in _STORE_GROCERY_TRANSLATIONS.items():
        if code == "en":
            continue
        session.add(
            ServiceTranslation(
                service_id=grocery.id, language_code=code, name=name, description=None
            )
        )
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create_resp = await ac.post(
            "/api/v1/stores/", json={"name": "Locale Mart", "address": make_address()}
        )
        assert create_resp.status_code == 200, create_resp.text
        sid = create_resp.json()["id"]
        get_resp = await ac.get(
            f"/api/v1/stores/{sid}", headers={"Accept-Language": lang}
        )
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert any(s["name"] == expected for s in body["services"]), body["services"]


@pytest.mark.asyncio
async def test_seller_cannot_create_second_store(override_as_seller: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        first = {"name": "First", "address": make_address()}
        r1 = await ac.post("/api/v1/stores/", json=first)
        assert r1.status_code == 200, r1.text
        second = {"name": "Second", "address": make_address(pincode="400099")}
        r2 = await ac.post("/api/v1/stores/", json=second)
    assert r2.status_code == 409
    assert "one" in r2.json()["detail"].lower()
