from typing import Any, AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_admin, get_current_user
from app.models.base import User, UserRole
from app.models.seller import SellerProfile, VerificationStatus
from tests._helpers import make_address

mock_admin = User(
    id=50, email="admin-apps@kb.com", full_name="Apps Admin",
    role=UserRole.Admin, is_active=True,
)
mock_seller_pending = User(
    id=51, email="pending@kb.com", full_name="Pending Seller",
    role=UserRole.Seller, is_active=True,
)
mock_seller_approved = User(
    id=52, email="approved@kb.com", full_name="Approved Seller",
    role=UserRole.Seller, is_active=True,
)
mock_seller_rejected = User(
    id=53, email="rejected@kb.com", full_name="Rejected Seller",
    role=UserRole.Seller, is_active=True,
)


def _profile(user_id: int | None, status: VerificationStatus, reason: str | None = None) -> SellerProfile:
    assert user_id is not None
    return SellerProfile(
        user_id=user_id,
        business_name=f"Biz {user_id}",
        business_category="grocery",
        phone="9876543210",
        gst_number="29ABCDE1234F1Z5",
        fssai_license="10020042000015",
        bank_account_number="123456789012",
        bank_ifsc="SBIN0001234",
        verification_status=status,
        rejection_reason=reason,
        **make_address(),
    )


@pytest.fixture(autouse=True)
async def seed_users_and_profiles(session: AsyncSession) -> AsyncGenerator[None, None]:
    session.add(User(**mock_admin.model_dump()))
    session.add(User(**mock_seller_pending.model_dump()))
    session.add(User(**mock_seller_approved.model_dump()))
    session.add(User(**mock_seller_rejected.model_dump()))
    await session.flush()
    session.add(_profile(mock_seller_pending.id, VerificationStatus.Pending))
    session.add(_profile(mock_seller_approved.id, VerificationStatus.Approved))
    session.add(_profile(mock_seller_rejected.id, VerificationStatus.Rejected, "Invalid GST"))
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
async def test_list_default_returns_pending_only(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sellers/admin/applications")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["verification_status"] == "pending"
    assert data[0]["email"] == "pending@kb.com"
    assert data[0]["full_name"] == "Pending Seller"
    assert data[0]["seller_id"] == mock_seller_pending.id
    assert "submitted_at" in data[0]


@pytest.mark.asyncio
async def test_list_filter_approved(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sellers/admin/applications?status=approved")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["verification_status"] == "approved"


@pytest.mark.asyncio
async def test_list_filter_rejected(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sellers/admin/applications?status=rejected")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["verification_status"] == "rejected"
    assert data[0]["rejection_reason"] == "Invalid GST"


@pytest.mark.asyncio
async def test_list_all(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sellers/admin/applications?status=all")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3


@pytest.mark.asyncio
async def test_list_invalid_status_returns_400(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sellers/admin/applications?status=bogus")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_requires_admin() -> None:
    app.dependency_overrides[get_current_user] = lambda: mock_seller_pending
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/sellers/admin/applications")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_counts_returns_grouped_totals(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sellers/admin/applications/counts")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"pending": 1, "approved": 1, "rejected": 1, "total": 3}


@pytest.mark.asyncio
async def test_counts_requires_admin() -> None:
    app.dependency_overrides[get_current_user] = lambda: mock_seller_pending
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/sellers/admin/applications/counts")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_counts_zero_when_no_profiles(
    override_as_admin: Any, session: AsyncSession
) -> None:
    from sqlmodel import delete
    await session.exec(delete(SellerProfile))
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sellers/admin/applications/counts")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"pending": 0, "approved": 0, "rejected": 0, "total": 0}


@pytest.mark.asyncio
async def test_revoke_approved_seller(override_as_admin: Any) -> None:
    """Revoking an approved seller = calling reject with a reason."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/admin/{mock_seller_approved.id}/verify",
            json={"action": "reject", "rejection_reason": "Fraud detected post-approval"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verification_status"] == "rejected"
    assert data["rejection_reason"] == "Fraud detected post-approval"
