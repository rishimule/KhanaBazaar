from typing import Any, AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_admin, get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import Service, ServiceTranslation
from app.models.profile import SellerProfile, SellerProfileService, VerificationStatus
from tests._helpers import make_address
from tests.conftest import test_engine

mock_admin = User(
    id=50, email="admin-apps@kb.com",
    role=UserRole.Admin, is_active=True,
)
mock_seller_pending = User(
    id=51, email="pending@kb.com",
    role=UserRole.Seller, is_active=True,
)
mock_seller_approved = User(
    id=52, email="approved@kb.com",
    role=UserRole.Seller, is_active=True,
)
mock_seller_rejected = User(
    id=53, email="rejected@kb.com",
    role=UserRole.Seller, is_active=True,
)


async def _make_profile(
    session: AsyncSession,
    user_id: int | None,
    first_name: str,
    last_name: str | None,
    phone: str,
    status: VerificationStatus,
    reason: str | None = None,
) -> SellerProfile:
    assert user_id is not None
    address = Address(**make_address())
    session.add(address)
    await session.flush()
    profile = SellerProfile(
        user_id=user_id,
        first_name=first_name,
        last_name=last_name,
        business_name=f"Biz {user_id}",
        phone=phone,
        gst_number="29ABCDE1234F1Z5",
        fssai_license="10020042000015",
        bank_account_number="123456789012",
        bank_ifsc="SBIN0001234",
        verification_status=status,
        rejection_reason=reason,
        business_address_id=address.id,
    )
    session.add(profile)
    await session.flush()
    return profile


@pytest.fixture(autouse=True)
async def seed_users_and_profiles(session: AsyncSession) -> AsyncGenerator[None, None]:
    session.add(User(**mock_admin.model_dump()))
    session.add(User(**mock_seller_pending.model_dump()))
    session.add(User(**mock_seller_approved.model_dump()))
    session.add(User(**mock_seller_rejected.model_dump()))
    await session.flush()
    pending_profile = await _make_profile(
        session, mock_seller_pending.id, "Pending", "Seller", "9876543210", VerificationStatus.Pending,
    )
    approved_profile = await _make_profile(
        session, mock_seller_approved.id, "Approved", "Seller", "9876543211", VerificationStatus.Approved,
    )
    rejected_profile = await _make_profile(
        session, mock_seller_rejected.id, "Rejected", "Seller", "9876543212",
        VerificationStatus.Rejected, "Invalid GST",
    )

    grocery = Service(slug="grocery", is_active=True, sort_order=0)
    session.add(grocery)
    await session.flush()
    session.add(
        ServiceTranslation(
            service_id=grocery.id, language_code="en", name="Grocery"
        )
    )
    await session.flush()
    grocery_id = grocery.id

    for profile in (pending_profile, approved_profile, rejected_profile):
        session.add(SellerProfileService(seller_profile_id=profile.id, service_id=grocery_id))

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
    await session.exec(delete(SellerProfileService))
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


@pytest.mark.asyncio
async def test_admin_applications_include_services(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sellers/admin/applications?status=pending")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1
    row = body[0]
    assert "business_category" not in row
    assert isinstance(row["services"], list)
    assert any(s["slug"] == "grocery" for s in row["services"])


@pytest.fixture
async def seeded_pharmacy_service_id_in_apps() -> int:
    async with AsyncSession(test_engine) as s:
        pharmacy = Service(slug="pharmacy", is_active=True, sort_order=1)
        s.add(pharmacy)
        await s.flush()
        pharmacy_id: int = pharmacy.id  # type: ignore[assignment]
        s.add(ServiceTranslation(
            service_id=pharmacy_id, language_code="en", name="Pharmacy"
        ))
        await s.commit()
        return pharmacy_id


@pytest.mark.asyncio
async def test_admin_set_services_replaces_set(
    override_as_admin: Any, seeded_pharmacy_service_id_in_apps: int,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/admin/{mock_seller_pending.id}/services",
            json={"service_ids": [seeded_pharmacy_service_id_in_apps]},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["seller_id"] == mock_seller_pending.id
    assert {s["slug"] for s in body["services"]} == {"pharmacy"}

    # Verify junction rows in DB
    async with AsyncSession(test_engine) as s:
        profile = (await s.exec(
            select(SellerProfile).where(SellerProfile.user_id == mock_seller_pending.id)
        )).first()
        rows = (await s.exec(
            select(SellerProfileService).where(
                SellerProfileService.seller_profile_id == profile.id
            )
        )).all()
        assert {r.service_id for r in rows} == {seeded_pharmacy_service_id_in_apps}


@pytest.mark.asyncio
async def test_admin_set_services_rejects_empty(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/admin/{mock_seller_pending.id}/services",
            json={"service_ids": []},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_admin_set_services_unknown_seller(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            "/api/v1/sellers/admin/99999/services",
            json={"service_ids": [1]},
        )
    assert resp.status_code == 404
