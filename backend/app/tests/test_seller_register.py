# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import (
    create_seller_email_token,
    create_seller_signup_token,
)
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import Service, ServiceTranslation
from app.models.profile import SellerProfile
from tests._helpers import make_address


@pytest.fixture
async def seeded_grocery_service_id(session: AsyncSession) -> int:
    service = Service(slug="grocery", is_active=True, sort_order=0)
    session.add(service)
    await session.flush()
    session.add(
        ServiceTranslation(
            service_id=service.id, language_code="en", name="Grocery"
        )
    )
    await session.flush()
    assert service.id is not None
    sid: int = service.id
    await session.commit()
    return sid


def _register_payload(service_ids: list[int], **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "full_name": "Priya Verma",
        "business_name": "Priya's Grocery",
        "service_ids": service_ids,
        "address": make_address(),
        "gst_number": "29ABCDE1234F1Z5",
        "fssai_license": "10020042000015",
        "bank_account_number": "123456789012",
        "bank_ifsc": "SBIN0001234",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_seller_register_happy_path(seeded_grocery_service_id: int) -> None:
    signup_token = create_seller_signup_token("seller@test.com", "+919876543210")
    payload = _register_payload([seeded_grocery_service_id])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"signup_token": signup_token, **payload},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "access_token" in body
    assert body["user"]["email"] == "seller@test.com"


@pytest.mark.asyncio
async def test_seller_register_rejects_missing_address_line1(seeded_grocery_service_id: int) -> None:
    signup_token = create_seller_signup_token("bad@test.com", "+919876543210")
    bad_address = make_address(address_line1="")
    payload = _register_payload([seeded_grocery_service_id], address=bad_address)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"signup_token": signup_token, **payload},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_seller_register_rejects_invalid_pincode(seeded_grocery_service_id: int) -> None:
    signup_token = create_seller_signup_token("pin@test.com", "+919876543210")
    bad_address = make_address(pincode="12345")
    payload = _register_payload([seeded_grocery_service_id], address=bad_address)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"signup_token": signup_token, **payload},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_seller_register_duplicate_email(seeded_grocery_service_id: int) -> None:
    base = _register_payload([seeded_grocery_service_id])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        first = create_seller_signup_token("dup@test.com", "+919876543210")
        await ac.post("/api/v1/auth/seller/register", json={"signup_token": first, **base})
        # Second registration with the same email but a different phone — must
        # still 409 on email (email check runs before phone).
        second = create_seller_signup_token("dup@test.com", "+919876543211")
        resp = await ac.post(
            "/api/v1/auth/seller/register", json={"signup_token": second, **base}
        )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "email_already_registered"


@pytest.mark.asyncio
async def test_seller_register_duplicate_phone(
    session: AsyncSession, seeded_grocery_service_id: int
) -> None:
    """Defence in depth: even with a valid signup_token, register rejects
    a phone number that another SellerProfile already holds (race window
    after OTP verification)."""
    user = User(email="first@test.com", role=UserRole.Seller)
    session.add(user)
    await session.flush()
    address = Address(
        address_line1="A",
        city="X",
        state="Maharashtra",
        pincode="400001",
        country="India",
    )
    session.add(address)
    await session.flush()
    assert user.id is not None and address.id is not None
    session.add(
        SellerProfile(
            user_id=user.id,
            first_name="A",
            last_name="B",
            business_name="First",
            phone="+919876543210",
            business_address_id=address.id,
        )
    )
    await session.commit()

    signup_token = create_seller_signup_token("second@test.com", "+919876543210")
    payload = _register_payload([seeded_grocery_service_id])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"signup_token": signup_token, **payload},
        )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "phone_already_registered"


@pytest.mark.asyncio
async def test_seller_register_invalid_token(seeded_grocery_service_id: int) -> None:
    payload = _register_payload([seeded_grocery_service_id])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"signup_token": "not.a.real.token", **payload},
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_signup_token"


@pytest.mark.asyncio
async def test_seller_register_rejects_email_token_as_signup_token(
    seeded_grocery_service_id: int,
) -> None:
    """Replay protection: an email-stage token must not be accepted at /register."""
    bad_token = create_seller_email_token("x@test.com")
    payload = _register_payload([seeded_grocery_service_id])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"signup_token": bad_token, **payload},
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_signup_token"


@pytest.mark.asyncio
async def test_seller_register_rejects_empty_service_ids(seeded_grocery_service_id: int) -> None:
    signup_token = create_seller_signup_token("empty@test.com", "+919876543210")
    payload = _register_payload([])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"signup_token": signup_token, **payload},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_seller_register_persists_services(seeded_grocery_service_id: int) -> None:
    signup_token = create_seller_signup_token("persist@test.com", "+919876543210")
    payload = _register_payload([seeded_grocery_service_id])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"signup_token": signup_token, **payload},
        )
        assert resp.status_code == 200, resp.text

    from sqlmodel import select

    from app.models.profile import SellerProfileService
    from tests.conftest import test_engine

    async with AsyncSession(test_engine) as s:
        profile = (await s.exec(select(SellerProfile))).first()
        assert profile is not None and profile.id is not None
        rows = (
            await s.exec(
                select(SellerProfileService).where(
                    SellerProfileService.seller_profile_id == profile.id
                )
            )
        ).all()
        assert {r.service_id for r in rows} == {seeded_grocery_service_id}


@pytest.mark.asyncio
async def test_seller_register_rejects_unknown_service_id(seeded_grocery_service_id: int) -> None:
    signup_token = create_seller_signup_token("bad-svc@test.com", "+919876543210")
    payload = _register_payload([99999])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"signup_token": signup_token, **payload},
        )
    assert resp.status_code == 400
    assert "service_ids" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_seller_register_accepts_null_compliance_and_bank_fields(
    seeded_grocery_service_id: int,
) -> None:
    signup_token = create_seller_signup_token("nobank@test.com", "+919876543210")
    payload = _register_payload(
        [seeded_grocery_service_id],
        gst_number=None,
        fssai_license=None,
        bank_account_number=None,
        bank_ifsc=None,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"signup_token": signup_token, **payload},
        )
    assert resp.status_code == 200, resp.text

    from sqlmodel import select

    from tests.conftest import test_engine

    async with AsyncSession(test_engine) as s:
        profile = (await s.exec(select(SellerProfile))).first()
        assert profile is not None
        assert profile.gst_number is None
        assert profile.fssai_license is None
        assert profile.bank_account_number is None
        assert profile.bank_ifsc is None


@pytest.mark.asyncio
async def test_seller_register_normalizes_empty_strings_to_null(
    seeded_grocery_service_id: int,
) -> None:
    signup_token = create_seller_signup_token("emptystr@test.com", "+919876543210")
    payload = _register_payload(
        [seeded_grocery_service_id],
        gst_number="",
        fssai_license="",
        bank_account_number="",
        bank_ifsc="",
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"signup_token": signup_token, **payload},
        )
    assert resp.status_code == 200, resp.text

    from sqlmodel import select

    from tests.conftest import test_engine

    async with AsyncSession(test_engine) as s:
        profile = (await s.exec(select(SellerProfile))).first()
        assert profile is not None
        assert profile.gst_number is None
        assert profile.fssai_license is None
        assert profile.bank_account_number is None
        assert profile.bank_ifsc is None
