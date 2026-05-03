import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import create_email_verification_token
from app.models.catalog import Service, ServiceTranslation
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
    sid = service.id
    await session.commit()
    return sid


def _register_payload(service_ids: list[int], **overrides) -> dict:
    payload = {
        "full_name": "Priya Verma",
        "phone": "9876543210",
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
    email_token = create_email_verification_token("seller@test.com")
    payload = _register_payload([seeded_grocery_service_id])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"email_token": email_token, **payload},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "access_token" in body
    assert body["user"]["email"] == "seller@test.com"


@pytest.mark.asyncio
async def test_seller_register_rejects_missing_address_line1(seeded_grocery_service_id: int) -> None:
    email_token = create_email_verification_token("bad@test.com")
    bad_address = make_address(address_line1="")
    payload = _register_payload([seeded_grocery_service_id], address=bad_address)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"email_token": email_token, **payload},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_seller_register_rejects_invalid_pincode(seeded_grocery_service_id: int) -> None:
    email_token = create_email_verification_token("pin@test.com")
    bad_address = make_address(pincode="12345")
    payload = _register_payload([seeded_grocery_service_id], address=bad_address)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"email_token": email_token, **payload},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_seller_register_duplicate_email(seeded_grocery_service_id: int) -> None:
    payload = {"email_token": create_email_verification_token("dup@test.com"), **_register_payload([seeded_grocery_service_id])}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post("/api/v1/auth/seller/register", json=payload)
        payload["email_token"] = create_email_verification_token("dup@test.com")
        resp = await ac.post("/api/v1/auth/seller/register", json=payload)
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "email_already_registered"


@pytest.mark.asyncio
async def test_seller_register_invalid_token(seeded_grocery_service_id: int) -> None:
    payload = _register_payload([seeded_grocery_service_id])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"email_token": "not.a.real.token", **payload},
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_email_token"


@pytest.mark.asyncio
async def test_seller_register_wrong_token_type(seeded_grocery_service_id: int) -> None:
    from datetime import datetime, timedelta, timezone

    import jwt as pyjwt

    from app.core.config import settings

    bad_token = pyjwt.encode(
        {"sub": "x@test.com", "type": "access", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    payload = _register_payload([seeded_grocery_service_id])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"email_token": bad_token, **payload},
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_email_token"


@pytest.mark.asyncio
async def test_seller_register_rejects_empty_service_ids(seeded_grocery_service_id: int) -> None:
    email_token = create_email_verification_token("empty@test.com")
    payload = _register_payload([])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"email_token": email_token, **payload},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_seller_register_persists_services(seeded_grocery_service_id: int) -> None:
    email_token = create_email_verification_token("persist@test.com")
    payload = _register_payload([seeded_grocery_service_id])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"email_token": email_token, **payload},
        )
        assert resp.status_code == 200, resp.text

    from app.models.profile import SellerProfile, SellerProfileService
    from sqlmodel import select

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
    email_token = create_email_verification_token("bad-svc@test.com")
    payload = _register_payload([99999])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"email_token": email_token, **payload},
        )
    assert resp.status_code == 400
    assert "service_ids" in resp.json()["detail"]
