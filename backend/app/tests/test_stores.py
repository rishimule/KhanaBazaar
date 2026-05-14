# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Any, AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_admin, get_current_seller, get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import Service, ServiceTranslation
from app.models.profile import SellerProfile, SellerProfileService, VerificationStatus
from app.models.store import Store
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
        svc_resp = await ac.get("/api/v1/catalog/services")
        assert svc_resp.status_code == 200
        grocery = next(s for s in svc_resp.json() if s["slug"] == "grocery")

        cat_data = {"service_id": grocery["id"], "name": "Dairy", "description": "Milk products"}
        cat_resp = await ac.post("/api/v1/catalog/admin/categories", json=cat_data)
        assert cat_resp.status_code == 200, cat_resp.text
        category = cat_resp.json()
        assert category["name"] == "Dairy"

        sub_data = {"category_id": category["id"], "name": "Butter"}
        sub_resp = await ac.post("/api/v1/catalog/admin/subcategories", json=sub_data)
        assert sub_resp.status_code == 200, sub_resp.text
        subcategory = sub_resp.json()

        prod_data = {
            "subcategory_id": subcategory["id"],
            "name": "Amul Butter 100g",
            "description": "Delicious butter",
            "base_price": 55.0,
        }
        prod_resp = await ac.post("/api/v1/catalog/admin/products", json=prod_data)
        assert prod_resp.status_code == 200, prod_resp.text
        product = prod_resp.json()
        assert product["name"] == "Amul Butter 100g"
        assert product["subcategory_id"] == subcategory["id"]


@pytest.mark.asyncio
async def test_seller_can_create_store(override_as_seller: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        store_data = {"name": "Rishi's Supermarket", "address": make_address()}
        store_resp = await ac.post("/api/v1/stores/", json=store_data)
        assert store_resp.status_code == 200
        store = store_resp.json()
        assert store["name"] == "Rishi's Supermarket"
        assert store["seller_id"] == mock_seller.id
        sent_address: dict[str, Any] = store_data["address"]  # type: ignore[assignment]
        for k, v in sent_address.items():
            assert store["address"][k] == v


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
    body_addr = get_resp.json()["address"]
    sent_address: dict[str, Any] = store_data["address"]  # type: ignore[assignment]
    for k, v in sent_address.items():
        assert body_addr[k] == v


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


async def _seed_second_seller_with_services(
    session: AsyncSession,
    *,
    email: str,
    user_id: int,
    service_slugs: list[str],
    address_overrides: dict[str, object] | None = None,
) -> int:
    """Create a fresh user + seller profile, attach the given services, return the seller_profile_id.

    `user_id` is explicit because the autouse fixture inserts mock_admin (id=1)
    and mock_seller (id=2) with explicit ids, which does not advance the
    Postgres sequence — letting the sequence allocate would collide.
    """
    new_user = User(id=user_id, email=email, role=UserRole.Seller, is_active=True)
    session.add(new_user)
    await session.flush()
    assert new_user.id is not None

    addr = Address(**make_address(**(address_overrides or {})))
    session.add(addr)
    await session.flush()
    assert addr.id is not None

    profile = SellerProfile(
        user_id=new_user.id,
        first_name="Seller",
        last_name=None,
        business_name=f"Biz {email}",
        phone="+919800000000",
        gst_number="06AAAAA1111A1Z1",
        fssai_license="44556677889900",
        bank_account_number="80100200300700",
        bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=addr.id,
    )
    session.add(profile)
    await session.flush()
    assert profile.id is not None

    for slug in service_slugs:
        row = await session.exec(select(Service).where(Service.slug == slug))
        svc = row.first()
        if svc is None:
            svc = Service(slug=slug)
            session.add(svc)
            await session.flush()
            assert svc.id is not None
            session.add(
                ServiceTranslation(
                    service_id=svc.id, language_code="en", name=slug.title()
                )
            )
            await session.flush()
        assert svc.id is not None
        session.add(
            SellerProfileService(seller_profile_id=profile.id, service_id=svc.id)
        )
    profile_id = profile.id
    await session.commit()
    return profile_id


async def _create_store_for_profile(
    session: AsyncSession,
    *,
    seller_profile_id: int,
    name: str,
    address_overrides: dict[str, object] | None = None,
    delivery_radius_km: float = 100.0,
) -> int:
    addr = Address(**make_address(**(address_overrides or {})))
    session.add(addr)
    await session.flush()
    assert addr.id is not None
    store = Store(
        name=name,
        seller_profile_id=seller_profile_id,
        address_id=addr.id,
        delivery_radius_km=delivery_radius_km,
    )
    session.add(store)
    await session.flush()
    assert store.id is not None
    store_id = store.id
    await session.commit()
    return store_id


@pytest.mark.asyncio
async def test_list_stores_filter_by_service(session: AsyncSession) -> None:
    seller_a_profile_row = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == mock_seller.id)
    )
    seller_a = seller_a_profile_row.first()
    assert seller_a is not None and seller_a.id is not None
    await _create_store_for_profile(
        session, seller_profile_id=seller_a.id, name="Grocery Store"
    )

    seller_b_id = await _seed_second_seller_with_services(
        session, email="pharma@kb.com", user_id=100, service_slugs=["pharmacy"]
    )
    await _create_store_for_profile(
        session, seller_profile_id=seller_b_id, name="Pharma Mart",
        address_overrides={"pincode": "400099"},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        grocery_resp = await ac.get("/api/v1/stores/?service=grocery")
        pharmacy_resp = await ac.get("/api/v1/stores/?service=pharmacy")

    assert grocery_resp.status_code == 200, grocery_resp.text
    grocery_bodies = grocery_resp.json()
    assert [s["name"] for s in grocery_bodies] == ["Grocery Store"]

    assert pharmacy_resp.status_code == 200, pharmacy_resp.text
    pharmacy_bodies = pharmacy_resp.json()
    assert [s["name"] for s in pharmacy_bodies] == ["Pharma Mart"]


@pytest.mark.asyncio
async def test_list_stores_filter_unknown_service() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/stores/?service=does-not-exist")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "unknown_service"


@pytest.mark.asyncio
async def test_list_stores_filter_inactive_service(session: AsyncSession) -> None:
    row = await session.exec(select(Service).where(Service.slug == "grocery"))
    grocery = row.first()
    assert grocery is not None
    grocery.is_active = False
    session.add(grocery)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/stores/?service=grocery")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "unknown_service"


@pytest.mark.asyncio
async def test_list_stores_filter_includes_stockless_offering(session: AsyncSession) -> None:
    seller_a_profile_row = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == mock_seller.id)
    )
    seller_a = seller_a_profile_row.first()
    assert seller_a is not None and seller_a.id is not None
    store_id = await _create_store_for_profile(
        session, seller_profile_id=seller_a.id, name="Empty Shelf Mart"
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/stores/?service=grocery")
    assert resp.status_code == 200, resp.text
    bodies = resp.json()
    assert any(s["id"] == store_id for s in bodies)


@pytest.mark.asyncio
async def test_list_stores_filter_with_distance_sort(session: AsyncSession) -> None:
    seller_a_profile_row = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == mock_seller.id)
    )
    seller_a = seller_a_profile_row.first()
    assert seller_a is not None and seller_a.id is not None
    near_id = await _create_store_for_profile(
        session,
        seller_profile_id=seller_a.id,
        name="Near Grocery",
        address_overrides={"latitude": 28.4595, "longitude": 77.0266},
    )

    seller_b_id = await _seed_second_seller_with_services(
        session, email="far-grocery@kb.com", user_id=101, service_slugs=["grocery"]
    )
    far_id = await _create_store_for_profile(
        session,
        seller_profile_id=seller_b_id,
        name="Far Grocery",
        address_overrides={
            "latitude": 28.6000,
            "longitude": 77.2500,
            "pincode": "110001",
        },
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/stores/?service=grocery&lat=28.4595&lng=77.0266"
            "&sort=distance&radius_km=100"
        )
    assert resp.status_code == 200, resp.text
    ids = [s["id"] for s in resp.json()]
    assert ids[0] == near_id
    assert far_id in ids
