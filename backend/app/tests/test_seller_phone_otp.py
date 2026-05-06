"""Tests for the seller phone-OTP endpoints."""
from collections.abc import AsyncGenerator

import jwt as pyjwt
import pytest
import redis.asyncio as aioredis
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.config import settings
from app.core.security import create_seller_email_token
from app.core.sms import get_sms_sender
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.profile import SellerProfile


class _RecorderSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, to: str, text: str) -> None:
        self.sent.append((to, text))


@pytest.fixture
def recorder() -> _RecorderSender:
    return _RecorderSender()


@pytest.fixture(autouse=True)
def _override_sms(recorder: _RecorderSender) -> AsyncGenerator[None, None]:
    app.dependency_overrides[get_sms_sender] = lambda: recorder
    yield
    app.dependency_overrides.pop(get_sms_sender, None)


@pytest.fixture(autouse=True)
async def _clean_phone_keys() -> AsyncGenerator[None, None]:
    # Drop the lru_cached Redis client so every test gets a connection bound
    # to its own event loop (pytest-asyncio creates one loop per function).
    from app.core.redis import _make_redis

    _make_redis.cache_clear()

    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    async for key in client.scan_iter("otp:phone:*"):
        await client.delete(key)
    yield
    async for key in client.scan_iter("otp:phone:*"):
        await client.delete(key)
    await client.aclose()
    _make_redis.cache_clear()


async def test_phone_request_happy_path(
    client: AsyncClient, recorder: _RecorderSender
) -> None:
    email_token = create_seller_email_token("seller@test.com")
    resp = await client.post(
        "/api/v1/auth/seller/phone/otp/request",
        json={"email_token": email_token, "phone": "+919876543210"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["expires_in"] == settings.OTP_TTL_SECONDS
    assert len(recorder.sent) == 1
    to, text = recorder.sent[0]
    assert to == "+919876543210"
    assert "verification code" in text.lower()


async def test_phone_request_rejects_invalid_format(client: AsyncClient) -> None:
    email_token = create_seller_email_token("seller@test.com")
    resp = await client.post(
        "/api/v1/auth/seller/phone/otp/request",
        json={"email_token": email_token, "phone": "9876543210"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_phone"


async def test_phone_request_rejects_bad_email_token(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/seller/phone/otp/request",
        json={"email_token": "not-a-jwt", "phone": "+919876543210"},
    )
    assert resp.status_code == 400


async def test_phone_request_rejects_duplicate_phone(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = User(email="existing@test.com", role=UserRole.Seller)
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
    assert user.id is not None
    assert address.id is not None
    session.add(
        SellerProfile(
            user_id=user.id,
            first_name="A",
            last_name="B",
            business_name="Existing Co",
            phone="+919876543210",
            business_address_id=address.id,
        )
    )
    await session.commit()

    email_token = create_seller_email_token("new-seller@test.com")
    resp = await client.post(
        "/api/v1/auth/seller/phone/otp/request",
        json={"email_token": email_token, "phone": "+919876543210"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "phone_already_registered"


async def test_phone_request_cooldown(client: AsyncClient) -> None:
    email_token = create_seller_email_token("seller@test.com")
    body = {"email_token": email_token, "phone": "+919876543210"}
    first = await client.post("/api/v1/auth/seller/phone/otp/request", json=body)
    assert first.status_code == 200
    second = await client.post("/api/v1/auth/seller/phone/otp/request", json=body)
    assert second.status_code == 429
    detail = second.json()["detail"]
    assert detail["error"] == "rate_limited"
    assert "retry_after" in detail


# ---- verify-endpoint tests added in Task 7 -------------------------------


def _extract_code(text: str) -> str:
    return text.split("verification code is: ")[1].split("\n")[0]


async def test_phone_verify_returns_signup_token(
    client: AsyncClient, recorder: _RecorderSender
) -> None:
    email_token = create_seller_email_token("seller@test.com")
    phone = "+919876543210"
    await client.post(
        "/api/v1/auth/seller/phone/otp/request",
        json={"email_token": email_token, "phone": phone},
    )
    code = _extract_code(recorder.sent[-1][1])
    resp = await client.post(
        "/api/v1/auth/seller/phone/otp/verify",
        json={"email_token": email_token, "phone": phone, "code": code},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "signup_token" in body
    decoded = pyjwt.decode(
        body["signup_token"], settings.JWT_SECRET, algorithms=["HS256"]
    )
    assert decoded["type"] == "seller_signup"
    assert decoded["sub"] == "seller@test.com"
    assert decoded["phone"] == phone


async def test_phone_verify_wrong_code(
    client: AsyncClient, recorder: _RecorderSender
) -> None:
    email_token = create_seller_email_token("seller@test.com")
    phone = "+919876543210"
    await client.post(
        "/api/v1/auth/seller/phone/otp/request",
        json={"email_token": email_token, "phone": phone},
    )
    resp = await client.post(
        "/api/v1/auth/seller/phone/otp/verify",
        json={"email_token": email_token, "phone": phone, "code": "000000"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_code"


async def test_phone_verify_too_many_attempts(
    client: AsyncClient, recorder: _RecorderSender
) -> None:
    email_token = create_seller_email_token("seller@test.com")
    phone = "+919876543210"
    await client.post(
        "/api/v1/auth/seller/phone/otp/request",
        json={"email_token": email_token, "phone": phone},
    )
    last = None
    for _ in range(settings.OTP_MAX_ATTEMPTS):
        last = await client.post(
            "/api/v1/auth/seller/phone/otp/verify",
            json={"email_token": email_token, "phone": phone, "code": "000000"},
        )
    assert last is not None
    assert last.status_code == 429
    assert last.json()["detail"]["error"] == "too_many_attempts"


async def test_phone_verify_no_code_issued(client: AsyncClient) -> None:
    email_token = create_seller_email_token("seller@test.com")
    resp = await client.post(
        "/api/v1/auth/seller/phone/otp/verify",
        json={
            "email_token": email_token,
            "phone": "+919876543210",
            "code": "123456",
        },
    )
    assert resp.status_code == 410
    assert resp.json()["detail"]["error"] == "code_expired_or_used"
