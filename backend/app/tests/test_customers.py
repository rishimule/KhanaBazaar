# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
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
from app.models.profile import (
    CustomerAddress,
    CustomerProfile,
    SellerProfile,
    VerificationStatus,
)
from tests._helpers import make_address

mock_customer = User(
    id=101, email="customer@kb.com", role=UserRole.Customer, is_active=True
)
mock_other_customer = User(
    id=102, email="other@kb.com", role=UserRole.Customer, is_active=True
)
mock_seller = User(
    id=103,
    email="seller-customer-api@kb.com",
    role=UserRole.Seller,
    is_active=True,
)
mock_admin = User(
    id=104, email="admin-customer-api@kb.com", role=UserRole.Admin, is_active=True
)
mock_orphan_customer = User(
    id=105, email="orphan@kb.com", role=UserRole.Customer, is_active=True
)


async def _seed_customer_profile(
    session: AsyncSession,
    user: User,
    first_name: str,
    last_name: str | None,
    phone: str | None,
) -> CustomerProfile:
    profile = CustomerProfile(
        user_id=user.id,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
    )
    session.add(profile)
    await session.flush()
    return profile


async def _seed_customer_address(
    session: AsyncSession,
    profile: CustomerProfile,
    *,
    label: str | None = "Home",
    is_default: bool = False,
    pincode: str = "122001",
) -> CustomerAddress:
    address = Address(**make_address(pincode=pincode))
    session.add(address)
    await session.flush()
    customer_address = CustomerAddress(
        customer_profile_id=profile.id,
        address_id=address.id,
        label=label,
        is_default=is_default,
    )
    session.add(customer_address)
    await session.flush()
    return customer_address


@pytest.fixture(autouse=True)
async def seed_users_and_profiles(
    session: AsyncSession,
) -> AsyncGenerator[None, None]:
    session.add(User(**mock_customer.model_dump()))
    session.add(User(**mock_other_customer.model_dump()))
    session.add(User(**mock_seller.model_dump()))
    session.add(User(**mock_admin.model_dump()))
    session.add(User(**mock_orphan_customer.model_dump()))
    await session.flush()

    customer_profile = await _seed_customer_profile(
        session,
        mock_customer,
        first_name="Asha",
        last_name="Patel",
        phone="9876543210",
    )
    other_profile = await _seed_customer_profile(
        session,
        mock_other_customer,
        first_name="Other",
        last_name=None,
        phone="9876543211",
    )
    await _seed_customer_address(
        session,
        customer_profile,
        label="Home",
        is_default=True,
        pincode="122001",
    )
    await _seed_customer_address(
        session,
        other_profile,
        label="Other Home",
        is_default=False,
        pincode="400001",
    )

    seller_address = Address(**make_address(pincode="560001"))
    session.add(seller_address)
    await session.flush()
    session.add(
        SellerProfile(
            user_id=mock_seller.id,
            first_name="Seller",
            last_name="User",
            business_name="Seller Store",
            business_category="grocery",
            phone="+919811110000",
            gst_number="06AAAAA1111A1Z1",
            fssai_license="44556677889900",
            bank_account_number="80100200300700",
            bank_ifsc="HDFC0000001",
            verification_status=VerificationStatus.Approved,
            business_address_id=seller_address.id,
        )
    )

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


@pytest.fixture
def override_as_admin() -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def override_as_orphan_customer() -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: mock_orphan_customer
    yield
    app.dependency_overrides.pop(get_current_user, None)


async def test_guest_cannot_fetch_customer_profile() -> None:
    app.dependency_overrides.pop(get_current_user, None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/customers/me")
    assert resp.status_code == 401


async def test_seller_cannot_fetch_customer_profile(override_as_seller: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/customers/me")
    assert resp.status_code == 403


async def test_admin_cannot_fetch_customer_profile(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/customers/me")
    assert resp.status_code == 403


async def test_customer_without_profile_returns_404(
    override_as_orphan_customer: Any,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/customers/me")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Customer profile not found"}


async def test_customer_can_fetch_profile(override_as_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/customers/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == mock_customer.id
    assert data["email"] == "customer@kb.com"
    assert data["first_name"] == "Asha"
    assert data["last_name"] == "Patel"
    assert data["phone"] == "9876543210"
    assert len(data["addresses"]) == 1
    assert data["addresses"][0]["label"] == "Home"
    assert data["addresses"][0]["is_default"] is True
    assert data["addresses"][0]["address"]["pincode"] == "122001"


async def test_customer_can_update_profile_fields(override_as_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            "/api/v1/customers/me",
            json={
                "first_name": "Priya",
                "last_name": None,
                "phone": "9876500000",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["first_name"] == "Priya"
    assert data["last_name"] is None
    assert data["phone"] == "9876500000"
    assert data["email"] == "customer@kb.com"


async def test_customer_cannot_update_email(override_as_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            "/api/v1/customers/me",
            json={"first_name": "Asha", "email": "changed@example.com"},
        )
    assert resp.status_code == 422


async def test_customer_can_add_address(override_as_customer: Any) -> None:
    payload = {
        "label": "Work",
        "is_default": False,
        "address": make_address(
            address_line1="55 Office Park", pincode="560001", state="Karnataka"
        ),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/customers/me/addresses", json=payload)
    assert resp.status_code == 200
    addresses = resp.json()["addresses"]
    assert len(addresses) == 2
    assert any(
        addr["label"] == "Work" and addr["address"]["pincode"] == "560001"
        for addr in addresses
    )


async def test_invalid_address_payload_returns_422(override_as_customer: Any) -> None:
    payload = {
        "label": "Invalid",
        "is_default": False,
        "address": make_address(pincode="000001"),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/customers/me/addresses", json=payload)
    assert resp.status_code == 422


async def test_customer_can_edit_owned_address(override_as_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        before = await ac.get("/api/v1/customers/me")
        address_id = before.json()["addresses"][0]["id"]
        resp = await ac.put(
            f"/api/v1/customers/me/addresses/{address_id}",
            json={
                "label": "Family",
                "is_default": True,
                "address": make_address(
                    address_line1="99 Updated Road",
                    pincode="110001",
                    state="Delhi",
                ),
            },
        )
    assert resp.status_code == 200
    updated = resp.json()["addresses"][0]
    assert updated["label"] == "Family"
    assert updated["is_default"] is True
    assert updated["address"]["address_line1"] == "99 Updated Road"
    assert updated["address"]["pincode"] == "110001"


async def test_customer_cannot_edit_another_customers_address(
    override_as_customer: Any,
    session: AsyncSession,
) -> None:
    profile_result = await session.exec(
        select(CustomerProfile).where(CustomerProfile.user_id == mock_other_customer.id)
    )
    other_profile = profile_result.one()
    assert other_profile.id is not None
    result = await session.exec(
        select(CustomerAddress).where(
            CustomerAddress.customer_profile_id == other_profile.id
        )
    )
    other_address = result.one()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/api/v1/customers/me/addresses/{other_address.id}",
            json={
                "label": "Stolen",
                "is_default": False,
                "address": make_address(),
            },
        )
    assert resp.status_code == 404


async def test_customer_can_set_default_address(override_as_customer: Any) -> None:
    create_payload = {
        "label": "Office",
        "is_default": False,
        "address": make_address(
            address_line1="22 Office", pincode="560001", state="Karnataka"
        ),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create = await ac.post("/api/v1/customers/me/addresses", json=create_payload)
        new_address = next(
            addr for addr in create.json()["addresses"] if addr["label"] == "Office"
        )
        resp = await ac.post(
            f"/api/v1/customers/me/addresses/{new_address['id']}/default"
        )
    assert resp.status_code == 200
    addresses = resp.json()["addresses"]
    assert sum(1 for addr in addresses if addr["is_default"]) == 1
    assert next(addr for addr in addresses if addr["label"] == "Office")[
        "is_default"
    ] is True
    assert next(addr for addr in addresses if addr["label"] == "Home")[
        "is_default"
    ] is False


async def test_creating_default_address_clears_previous_default(
    override_as_customer: Any,
) -> None:
    payload = {
        "label": "Parents",
        "is_default": True,
        "address": make_address(
            address_line1="1 Parent Home", pincode="400001", state="Maharashtra"
        ),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/customers/me/addresses", json=payload)
    assert resp.status_code == 200
    addresses = resp.json()["addresses"]
    assert sum(1 for addr in addresses if addr["is_default"]) == 1
    assert next(addr for addr in addresses if addr["label"] == "Parents")[
        "is_default"
    ] is True


async def test_deleting_default_address_leaves_no_default(
    override_as_customer: Any,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        before = await ac.get("/api/v1/customers/me")
        default_address = next(addr for addr in before.json()["addresses"] if addr["is_default"])
        resp = await ac.delete(f"/api/v1/customers/me/addresses/{default_address['id']}")
    assert resp.status_code == 200
    assert resp.json()["addresses"] == []


async def test_deleting_non_owned_address_returns_404(
    override_as_customer: Any,
    session: AsyncSession,
) -> None:
    profile_result = await session.exec(
        select(CustomerProfile).where(CustomerProfile.user_id == mock_other_customer.id)
    )
    other_profile = profile_result.one()
    assert other_profile.id is not None
    result = await session.exec(
        select(CustomerAddress).where(
            CustomerAddress.customer_profile_id == other_profile.id
        )
    )
    other_address = result.one()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete(f"/api/v1/customers/me/addresses/{other_address.id}")
    assert resp.status_code == 404
