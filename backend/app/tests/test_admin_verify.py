from typing import Any, AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_admin, get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.profile import SellerProfile, VerificationStatus
from tests._helpers import make_address

mock_admin = User(
    id=20, email="admin@kb.com",
    role=UserRole.Admin, is_active=True,
)
mock_seller = User(
    id=21, email="sellerverify@kb.com",
    role=UserRole.Seller, is_active=True,
)


@pytest.fixture(autouse=True)
async def seed_users_and_profile(session: AsyncSession) -> AsyncGenerator[None, None]:
    session.add(User(**mock_admin.model_dump()))
    session.add(User(**mock_seller.model_dump()))
    await session.flush()
    address = Address(**make_address())
    session.add(address)
    await session.flush()
    session.add(SellerProfile(
        user_id=mock_seller.id,
        first_name="Verify",
        last_name="Seller",
        business_name="Verify Grocery",
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
def override_as_admin() -> Iterator[None]:
    app.dependency_overrides[get_current_admin] = lambda: mock_admin
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    yield
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_approve_seller(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/admin/{mock_seller.id}/verify",
            json={"action": "approve"},
        )
    assert resp.status_code == 200
    assert resp.json()["verification_status"] == "approved"


@pytest.mark.asyncio
async def test_admin_reject_seller_with_reason(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/admin/{mock_seller.id}/verify",
            json={"action": "reject", "rejection_reason": "GST number invalid"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verification_status"] == "rejected"
    assert data["rejection_reason"] == "GST number invalid"


@pytest.mark.asyncio
async def test_reject_without_reason_returns_400(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/admin/{mock_seller.id}/verify",
            json={"action": "reject"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_seller_cannot_verify_403() -> None:
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.patch(
                f"/api/v1/sellers/admin/{mock_seller.id}/verify",
                json={"action": "approve"},
            )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
