import pytest
from httpx import ASGITransport, AsyncClient

from app import app
from app.core.security import create_email_verification_token
from tests._helpers import make_address

REGISTER_PAYLOAD = {
    "full_name": "Priya Verma",
    "phone": "9876543210",
    "business_name": "Priya's Grocery",
    "business_category": "grocery",
    "address": make_address(),
    "gst_number": "29ABCDE1234F1Z5",
    "fssai_license": "10020042000015",
    "bank_account_number": "123456789012",
    "bank_ifsc": "SBIN0001234",
}


@pytest.mark.asyncio
async def test_seller_register_happy_path_returns_nested_address_on_profile() -> None:
    email_token = create_email_verification_token("seller@test.com")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"email_token": email_token, **REGISTER_PAYLOAD},
        )
        assert resp.status_code == 200
        token = resp.json()["access_token"]

        profile_resp = await ac.get(
            "/api/v1/sellers/me/profile",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert profile_resp.status_code == 200
    profile = profile_resp.json()
    assert profile["address"] == REGISTER_PAYLOAD["address"]


@pytest.mark.asyncio
async def test_seller_register_rejects_missing_address_line1() -> None:
    email_token = create_email_verification_token("bad@test.com")
    bad_address = make_address(address_line1="")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"email_token": email_token, **{**REGISTER_PAYLOAD, "address": bad_address}},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_seller_register_rejects_invalid_pincode() -> None:
    email_token = create_email_verification_token("pin@test.com")
    bad_address = make_address(pincode="12345")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"email_token": email_token, **{**REGISTER_PAYLOAD, "address": bad_address}},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_seller_register_duplicate_email() -> None:
    payload = {"email_token": create_email_verification_token("dup@test.com"), **REGISTER_PAYLOAD}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post("/api/v1/auth/seller/register", json=payload)
        payload["email_token"] = create_email_verification_token("dup@test.com")
        resp = await ac.post("/api/v1/auth/seller/register", json=payload)
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "email_already_registered"


@pytest.mark.asyncio
async def test_seller_register_invalid_token() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"email_token": "not.a.real.token", **REGISTER_PAYLOAD},
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_email_token"


@pytest.mark.asyncio
async def test_seller_register_wrong_token_type() -> None:
    from datetime import datetime, timedelta, timezone

    import jwt as pyjwt

    from app.core.config import settings

    bad_token = pyjwt.encode(
        {"sub": "x@test.com", "type": "access", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/seller/register",
            json={"email_token": bad_token, **REGISTER_PAYLOAD},
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_email_token"
