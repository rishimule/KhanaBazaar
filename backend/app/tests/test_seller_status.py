from typing import Any, AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_seller, get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import Service, ServiceTranslation
from app.models.profile import SellerProfile, SellerProfileService, VerificationStatus
from tests._helpers import make_address
from tests.conftest import test_engine

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
    profile = SellerProfile(
        user_id=mock_seller.id,
        first_name="Status",
        last_name="Seller",
        business_name="Status Grocery",
        phone="9876543210",
        gst_number="29ABCDE1234F1Z5",
        fssai_license="10020042000015",
        bank_account_number="123456789012",
        bank_ifsc="SBIN0001234",
        verification_status=VerificationStatus.Pending,
        business_address_id=address.id,
    )
    session.add(profile)
    await session.flush()

    grocery = Service(slug="grocery", is_active=True, sort_order=0)
    session.add(grocery)
    await session.flush()
    session.add(
        ServiceTranslation(
            service_id=grocery.id, language_code="en", name="Grocery"
        )
    )
    await session.flush()
    session.add(SellerProfileService(seller_profile_id=profile.id, service_id=grocery.id))
    await session.commit()
    yield


@pytest.fixture
def override_as_seller() -> Iterator[None]:
    app.dependency_overrides[get_current_seller] = lambda: mock_seller
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    yield
    app.dependency_overrides.pop(get_current_seller, None)
    app.dependency_overrides.pop(get_current_user, None)


async def _set_seller_status(session: AsyncSession, status: VerificationStatus) -> None:
    profile = (await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == mock_seller.id)
    )).first()
    assert profile is not None
    profile.verification_status = status
    await session.commit()


@pytest.fixture
async def seller_status_pending(session: AsyncSession) -> None:
    await _set_seller_status(session, VerificationStatus.Pending)


@pytest.fixture
async def seller_status_approved(session: AsyncSession) -> None:
    await _set_seller_status(session, VerificationStatus.Approved)


@pytest.fixture
async def seller_status_rejected(session: AsyncSession) -> None:
    await _set_seller_status(session, VerificationStatus.Rejected)


@pytest.fixture
async def seeded_pharmacy_service_id() -> int:
    async with AsyncSession(test_engine) as s:
        pharmacy = Service(slug="pharmacy", is_active=True, sort_order=1)
        s.add(pharmacy)
        await s.flush()
        await s.refresh(pharmacy)
        pid: int = pharmacy.id  # type: ignore[assignment]
        s.add(
            ServiceTranslation(
                service_id=pid, language_code="en", name="Pharmacy"
            )
        )
        await s.commit()
        return pid


def _patch_payload(**overrides: Any) -> dict:  # type: ignore[type-arg]
    payload: dict = {  # type: ignore[type-arg]
        "business_name": "Updated Grocery",
        "address": make_address(city="Mumbai", state="Maharashtra", pincode="400001"),
        "phone": "9876543211",
        "gst_number": "29ABCDE1234F1Z5",
        "fssai_license": "10020042000015",
        "bank_account_number": "123456789012",
        "bank_ifsc": "SBIN0001234",
    }
    payload.update(overrides)
    return payload


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
    assert "business_category" not in data
    assert isinstance(data["services"], list)
    assert any(s["slug"] == "grocery" for s in data["services"])
    assert any(s["name"] == "Grocery" for s in data["services"])
    assert data["phone"] == "9876543210"
    assert data["full_name"] == "Status Seller"


@pytest.mark.asyncio
async def test_patch_me_pending_can_change_services(
    override_as_seller: Any,
    seller_status_pending: None,
    seeded_pharmacy_service_id: int,
) -> None:
    pid = seeded_pharmacy_service_id
    body = _patch_payload(service_ids=[pid])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch("/api/v1/sellers/me/profile", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["verification_status"] == "pending"

    async with AsyncSession(test_engine) as s:
        profile = (await s.exec(select(SellerProfile).where(SellerProfile.user_id == mock_seller.id))).first()
        assert profile is not None
        rows = (await s.exec(select(SellerProfileService).where(SellerProfileService.seller_profile_id == profile.id))).all()
        assert {r.service_id for r in rows} == {pid}


@pytest.mark.asyncio
async def test_patch_me_rejected_can_change_services(
    override_as_seller: Any,
    seller_status_rejected: None,
    seeded_pharmacy_service_id: int,
) -> None:
    pid2 = seeded_pharmacy_service_id
    body = _patch_payload(service_ids=[pid2])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch("/api/v1/sellers/me/profile", json=body)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_patch_me_approved_cannot_change_services(
    override_as_seller: Any,
    seller_status_approved: None,
) -> None:
    body = _patch_payload(service_ids=[99999])  # any id; should be rejected before lookup
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch("/api/v1/sellers/me/profile", json=body)
    assert resp.status_code == 400
    assert "locked" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_patch_me_no_service_change_keeps_existing(
    override_as_seller: Any,
    seller_status_pending: None,
) -> None:
    """If service_ids omitted (Optional), existing services unchanged."""
    body = _patch_payload()  # no service_ids key
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch("/api/v1/sellers/me/profile", json=body)
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
