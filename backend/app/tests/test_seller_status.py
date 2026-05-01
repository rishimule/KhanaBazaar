from typing import Any, AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_seller, get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.profile import SellerProfile, VerificationStatus
from tests._helpers import make_address

mock_seller = User(
    id=10, email="sellerstatus@kb.com",
    role=UserRole.Seller, is_active=True,
)
mock_customer = User(
    id=11, email="cust@kb.com",
    role=UserRole.Customer, is_active=True,
)


@pytest.fixture(autouse=True)
async def seed_seller_with_profile(session: AsyncSession) -> AsyncGenerator[None, None]:
    session.add(User(**mock_seller.model_dump()))
    await session.flush()
    address = Address(**make_address())
    session.add(address)
    await session.flush()
    session.add(SellerProfile(
        user_id=mock_seller.id,
        first_name="Status",
        last_name="Seller",
        business_name="Status Grocery",
        business_category="grocery",
        phone="9876543210",
        gst_number="29ABCDE1234F1Z5",
        fssai_license="10020042000015",
        bank_account_number="123456789012",
        bank_ifsc="SBIN0001234",
        verification_status=VerificationStatus.Pending,
        business_address_id=address.id,
    ))
    await session.commit()
    yield


@pytest.fixture
def override_as_seller() -> Iterator[None]:
    app.dependency_overrides[get_current_seller] = lambda: mock_seller
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    yield
    app.dependency_overrides.pop(get_current_seller, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_seller_status_returns_pending(override_as_seller: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sellers/me/status")
    assert resp.status_code == 200
    assert resp.json()["verification_status"] == "pending"
    assert resp.json()["rejection_reason"] is None


@pytest.mark.asyncio
async def test_get_seller_profile_returns_fields(override_as_seller: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sellers/me/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert data["business_name"] == "Status Grocery"
    assert data["business_category"] == "grocery"
    assert data["phone"] == "9876543210"
    assert data["full_name"] == "Status Seller"


@pytest.mark.asyncio
async def test_update_profile_resets_status_to_pending(override_as_seller: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch("/api/v1/sellers/me/profile", json={
            "business_name": "Updated Grocery",
            "business_category": "pharmacy",
            "address": make_address(city="Mumbai", state="Maharashtra", pincode="400001"),
            "phone": "9876543211",
            "gst_number": "29ABCDE1234F1Z5",
            "fssai_license": "10020042000015",
            "bank_account_number": "123456789012",
            "bank_ifsc": "SBIN0001234",
        })
    assert resp.status_code == 200
    assert resp.json()["verification_status"] == "pending"


@pytest.mark.asyncio
async def test_customer_cannot_access_seller_status() -> None:
    app.dependency_overrides[get_current_user] = lambda: mock_customer
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/sellers/me/status")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
