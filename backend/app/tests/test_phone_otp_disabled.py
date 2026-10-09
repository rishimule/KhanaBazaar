# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Behaviour of the three phone-OTP chains when `PHONE_OTP_ENABLED` is False.

With no SMS transport bought, a phone code can never reach the user, so the
flag takes the number on trust: every `.../otp/request` endpoint keeps its
validation and returns the token its `verify` twin would have minted. These
tests pin the bypass AND the guards that must survive it — uniqueness and
rate limiting.

The default is True, so the existing suites cover the enabled path.

The fourth chain, customer signup (`/auth/customer/phone/otp/*`), is covered
in test_customer_signup_phone.py. Its verify step deliberately never
short-circuits: no client predates it, and a code-free mint would skip the
request path's uniqueness check and budgets.
"""
from collections.abc import AsyncIterator, Generator
from typing import Any

import jwt as pyjwt
import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core import redis as redis_module
from app.core.config import settings
from app.core.security import (
    create_seller_email_token,
    get_current_customer,
    get_current_seller,
    get_current_user,
)
from app.core.sms import SMSSender, get_sms_sender
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.profile import CustomerProfile, SellerProfile, VerificationStatus
from tests._helpers import make_address as _make_address_dict

pytestmark = pytest.mark.asyncio


class _RecordingSMS(SMSSender):
    """Records instead of sending, so a test can assert nothing went out."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, to: str, text: str) -> None:
        self.sent.append((to, text))


@pytest.fixture
def sms() -> _RecordingSMS:
    return _RecordingSMS()


@pytest.fixture(autouse=True)
def _override_sms(sms: _RecordingSMS) -> Generator[None, None, None]:
    app.dependency_overrides[get_sms_sender] = lambda: sms
    yield
    app.dependency_overrides.pop(get_sms_sender, None)


@pytest.fixture(autouse=True)
async def _fresh_redis_client() -> AsyncIterator[None]:
    """Rebind the lru_cached client to this test's event loop.

    `api/customers.py` calls `get_redis()` directly rather than through
    `Depends`, so it reaches the real Redis rather than conftest's FakeRedis.
    """
    redis_module._make_redis.cache_clear()
    yield
    redis_module._make_redis.cache_clear()


@pytest.fixture
def otp_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PHONE_OTP_ENABLED", False)


# --------------------------------------------------------------------------
# Seller signup — /auth/seller/phone/otp/*
# --------------------------------------------------------------------------


async def test_seller_request_mints_signup_token_and_sends_no_sms(
    client: AsyncClient, sms: _RecordingSMS, otp_disabled: None
) -> None:
    email_token = create_seller_email_token("bypass@test.com")
    resp = await client.post(
        "/api/v1/auth/seller/phone/otp/request",
        json={"email_token": email_token, "phone": "+919876500001"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["otp_required"] is False
    assert sms.sent == []
    decoded = pyjwt.decode(
        body["signup_token"], settings.JWT_SECRET, algorithms=["HS256"]
    )
    assert decoded["type"] == "seller_signup"
    assert decoded["sub"] == "bypass@test.com"
    assert decoded["phone"] == "+919876500001"


async def test_seller_request_reports_otp_required_when_enabled(
    client: AsyncClient, sms: _RecordingSMS
) -> None:
    """The flag's default path advertises itself too, so a client can branch."""
    email_token = create_seller_email_token("enabled@test.com")
    resp = await client.post(
        "/api/v1/auth/seller/phone/otp/request",
        json={"email_token": email_token, "phone": "+919876500002"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["otp_required"] is True
    assert "signup_token" not in body
    assert len(sms.sent) == 1


async def test_seller_request_still_rejects_invalid_phone(
    client: AsyncClient, otp_disabled: None
) -> None:
    email_token = create_seller_email_token("bypass@test.com")
    resp = await client.post(
        "/api/v1/auth/seller/phone/otp/request",
        json={"email_token": email_token, "phone": "9876500003"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_phone"


async def test_seller_request_still_rejects_registered_phone(
    client: AsyncClient, session: AsyncSession, otp_disabled: None
) -> None:
    user = User(email="taken-seller@test.com", role=UserRole.Seller)
    session.add(user)
    await session.flush()
    address = Address(**_make_address_dict())
    session.add(address)
    await session.flush()
    session.add(
        SellerProfile(
            user_id=user.id,
            first_name="A",
            last_name="B",
            business_name="Taken Co",
            phone="+919876500004",
            business_address_id=address.id,
            upi_vpa="seed@okaxis",
        )
    )
    await session.commit()

    resp = await client.post(
        "/api/v1/auth/seller/phone/otp/request",
        json={
            "email_token": create_seller_email_token("new@test.com"),
            "phone": "+919876500004",
        },
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "phone_already_registered"


async def test_seller_request_still_rate_limited(
    client: AsyncClient, otp_disabled: None
) -> None:
    """Without this, the `phone_already_registered` 409 is a free
    enumeration oracle — `request_otp`'s hourly budget no longer applies."""
    email_token = create_seller_email_token("flood@test.com")
    body = {"email_token": email_token, "phone": "+919876500005"}
    for _ in range(settings.OTP_MAX_PER_HOUR):
        ok = await client.post("/api/v1/auth/seller/phone/otp/request", json=body)
        assert ok.status_code == 200, ok.text
    over = await client.post("/api/v1/auth/seller/phone/otp/request", json=body)
    assert over.status_code == 429
    assert over.json()["detail"]["error"] == "rate_limited"


async def test_seller_verify_accepts_any_code(
    client: AsyncClient, otp_disabled: None
) -> None:
    """A client that ignores `otp_required` must still complete, rather than
    dying on `code_expired_or_used` against a code that was never stored."""
    email_token = create_seller_email_token("stale@test.com")
    resp = await client.post(
        "/api/v1/auth/seller/phone/otp/verify",
        json={
            "email_token": email_token,
            "phone": "+919876500006",
            "code": "000000",
        },
    )
    assert resp.status_code == 200, resp.text
    decoded = pyjwt.decode(
        resp.json()["signup_token"], settings.JWT_SECRET, algorithms=["HS256"]
    )
    assert decoded["phone"] == "+919876500006"


# --------------------------------------------------------------------------
# Customer profile phone — /customers/me/phone/otp/*
# --------------------------------------------------------------------------


async def _make_customer(
    session: AsyncSession, email: str
) -> tuple[User, CustomerProfile]:
    user = User(email=email, role=UserRole.Customer, is_active=True)
    session.add(user)
    await session.flush()
    assert user.id is not None
    profile = CustomerProfile(user_id=user.id, first_name="C")
    session.add(profile)
    await session.commit()
    await session.refresh(user)
    await session.refresh(profile)
    return user, profile


@pytest.fixture
async def customer(session: AsyncSession) -> AsyncIterator[User]:
    user, _ = await _make_customer(session, "bypass-customer@test.com")
    app.dependency_overrides[get_current_customer] = lambda: user
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield user
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
        app.dependency_overrides.pop(get_current_user, None)


async def test_customer_request_marks_verified_and_sends_no_sms(
    client: AsyncClient,
    session: AsyncSession,
    customer: User,
    sms: _RecordingSMS,
    otp_disabled: None,
) -> None:
    resp = await client.post(
        "/api/v1/customers/me/phone/otp/request",
        json={"phone": "+919876500011"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["otp_required"] is False
    assert body["profile"]["phone"] == "+919876500011"
    assert body["profile"]["phone_verified_at"] is not None
    assert sms.sent == []

    # The endpoint committed on its own session; this one still holds the
    # pre-request instance in its identity map (expire_on_commit=False).
    # Read the id out before expiring, or touching it lazy-loads sync-ly.
    user_id = customer.id
    session.expire_all()
    stored = (
        await session.exec(
            select(CustomerProfile).where(CustomerProfile.user_id == user_id)
        )
    ).first()
    assert stored is not None
    assert stored.phone == "+919876500011"
    assert stored.phone_verified_at is not None


async def test_customer_request_still_rejects_phone_in_use(
    client: AsyncClient,
    session: AsyncSession,
    customer: User,
    otp_disabled: None,
) -> None:
    _, other = await _make_customer(session, "other-customer@test.com")
    other.phone = "+919876500012"
    session.add(other)
    await session.commit()

    resp = await client.post(
        "/api/v1/customers/me/phone/otp/request",
        json={"phone": "+919876500012"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "phone_already_in_use"


async def test_customer_verify_accepts_any_code(
    client: AsyncClient, customer: User, otp_disabled: None
) -> None:
    resp = await client.post(
        "/api/v1/customers/me/phone/otp/verify",
        json={"phone": "+919876500013", "code": "000000"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["phone"] == "+919876500013"
    assert body["phone_verified_at"] is not None


async def test_customer_patch_phone_keeps_it_verified(
    client: AsyncClient, customer: User, otp_disabled: None
) -> None:
    """Otherwise editing the number in the profile form un-verifies it and
    drops the user into a modal that instantly verifies it again."""
    resp = await client.patch(
        "/api/v1/customers/me", json={"phone": "+919876500014"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["phone"] == "+919876500014"
    assert body["phone_verified_at"] is not None


async def test_customer_patch_clearing_phone_leaves_it_unverified(
    client: AsyncClient, customer: User, otp_disabled: None
) -> None:
    """Nothing to assume when there is no number."""
    resp = await client.patch("/api/v1/customers/me", json={"phone": None})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["phone"] is None
    assert body["phone_verified_at"] is None


# --------------------------------------------------------------------------
# Approved-seller phone change — /sellers/me/phone/otp/*
# --------------------------------------------------------------------------


@pytest.fixture
async def seller_auth(approved_seller: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    seller_user: User = approved_seller["user"]
    app.dependency_overrides[get_current_seller] = lambda: seller_user
    app.dependency_overrides[get_current_user] = lambda: seller_user
    try:
        yield approved_seller
    finally:
        app.dependency_overrides.pop(get_current_seller, None)
        app.dependency_overrides.pop(get_current_user, None)


async def test_phone_change_request_mints_token_and_sends_no_sms(
    client: AsyncClient,
    seller_auth: dict[str, Any],
    sms: _RecordingSMS,
    otp_disabled: None,
) -> None:
    resp = await client.post(
        "/api/v1/sellers/me/phone/otp/request", json={"phone": "+919876500021"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["otp_required"] is False
    assert sms.sent == []
    decoded = pyjwt.decode(
        body["phone_change_token"], settings.JWT_SECRET, algorithms=["HS256"]
    )
    assert decoded["type"] == "seller_phone_change"
    assert decoded["phone"] == "+919876500021"
    assert decoded["sub"] == str(seller_auth["user"].id)


async def test_phone_change_request_still_rejects_unchanged_phone(
    client: AsyncClient, seller_auth: dict[str, Any], otp_disabled: None
) -> None:
    resp = await client.post(
        "/api/v1/sellers/me/phone/otp/request",
        json={"phone": seller_auth["profile"].phone},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "phone_unchanged"


async def test_phone_change_request_still_rejects_taken_phone(
    client: AsyncClient,
    session: AsyncSession,
    seller_auth: dict[str, Any],
    otp_disabled: None,
) -> None:
    addr = Address(**_make_address_dict())
    session.add(addr)
    await session.flush()
    other = User(email="other-change@test.com", role=UserRole.Seller)
    session.add(other)
    await session.flush()
    session.add(
        SellerProfile(
            user_id=other.id,
            first_name="O",
            last_name="S",
            phone="+919876500022",
            business_name="Other",
            verification_status=VerificationStatus.Approved,
            business_address_id=addr.id,
            upi_vpa="seed@okaxis",
        )
    )
    await session.commit()

    resp = await client.post(
        "/api/v1/sellers/me/phone/otp/request", json={"phone": "+919876500022"}
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "phone_taken"


async def test_phone_change_verify_accepts_any_code(
    client: AsyncClient, seller_auth: dict[str, Any], otp_disabled: None
) -> None:
    resp = await client.post(
        "/api/v1/sellers/me/phone/otp/verify",
        json={"phone": "+919876500023", "code": "000000"},
    )
    assert resp.status_code == 200, resp.text
    decoded = pyjwt.decode(
        resp.json()["phone_change_token"],
        settings.JWT_SECRET,
        algorithms=["HS256"],
    )
    assert decoded["phone"] == "+919876500023"


async def test_customer_patch_junk_phone_is_not_marked_verified(
    client: AsyncClient, customer: User, otp_disabled: None
) -> None:
    """PATCH /me never validated the phone. Assuming an unparseable string is
    a verified mobile would feed junk to every verified-phone gate."""
    resp = await client.patch(
        "/api/v1/customers/me", json={"phone": "not a phone"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["phone"] == "not a phone"
    assert body["phone_verified_at"] is None


async def test_customer_patch_phone_is_stored_canonical(
    client: AsyncClient, customer: User, otp_disabled: None
) -> None:
    """A number the flag marks verified must be stored in the same canonical
    form the OTP path would have written, or uniqueness checks miss it."""
    resp = await client.patch(
        "/api/v1/customers/me", json={"phone": "+91 98765-00015"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["phone"] == "+919876500015"
    assert body["phone_verified_at"] is not None
