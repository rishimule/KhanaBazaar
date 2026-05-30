# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.security import (
    create_seller_phone_change_token,
    create_seller_signup_token,
    decode_seller_phone_change_token,
)


def test_phone_change_token_roundtrip():
    tok = create_seller_phone_change_token(42, "+919811119999")
    uid, phone = decode_seller_phone_change_token(tok)
    assert uid == 42
    assert phone == "+919811119999"


def test_phone_change_token_rejects_wrong_type():
    # A signup token must NOT be accepted as a phone-change token.
    signup = create_seller_signup_token("a@b.test", "+919811119999")
    with pytest.raises(HTTPException) as excinfo:
        decode_seller_phone_change_token(signup)
    assert excinfo.value.status_code == 400


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------
from typing import AsyncIterator  # noqa: E402

from httpx import AsyncClient  # noqa: E402

from app import app  # noqa: E402
from app.core.security import (  # noqa: E402
    get_current_seller,
    get_current_user,
)
from app.models.address import Address  # noqa: E402
from app.models.base import User, UserRole  # noqa: E402
from app.models.profile import SellerProfile, VerificationStatus  # noqa: E402
from tests._helpers import make_address as _make_address_dict  # noqa: E402


@pytest.fixture
async def _seller_auth(approved_seller: dict) -> AsyncIterator[dict]:
    seller_user: User = approved_seller["user"]
    app.dependency_overrides[get_current_seller] = lambda: seller_user
    app.dependency_overrides[get_current_user] = lambda: seller_user
    try:
        yield approved_seller
    finally:
        app.dependency_overrides.pop(get_current_seller, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_otp_request_rejects_unchanged_phone(
    _seller_auth: dict, client: AsyncClient
) -> None:
    current = _seller_auth["profile"].phone
    res = await client.post(
        "/api/v1/sellers/me/phone/otp/request", json={"phone": current}
    )
    assert res.status_code == 400, res.text
    assert res.json()["detail"]["error"] == "phone_unchanged"


@pytest.mark.asyncio
async def test_otp_request_rejects_phone_taken_by_other_seller(
    _seller_auth: dict, session, client: AsyncClient
) -> None:
    taken = "+919811119999"
    addr = Address(**_make_address_dict())
    session.add(addr)
    await session.flush()
    other = User(email="other-otp@x.test", role=UserRole.Seller)
    session.add(other)
    await session.flush()
    session.add(
        SellerProfile(
            user_id=other.id, first_name="O", last_name="S", phone=taken,
            business_name="Other", verification_status=VerificationStatus.Approved,
            business_address_id=addr.id,
        )
    )
    await session.commit()
    res = await client.post(
        "/api/v1/sellers/me/phone/otp/request", json={"phone": taken}
    )
    assert res.status_code == 409, res.text
    assert res.json()["detail"]["error"] == "phone_taken"


@pytest.mark.asyncio
async def test_otp_request_then_verify_returns_token(
    _seller_auth: dict, client: AsyncClient, monkeypatch
) -> None:
    sent = {}

    async def _fake_request_otp(identifier, redis, *, namespace):
        sent["code"] = "123456"
        sent["id"] = identifier
        return "123456"

    async def _fake_verify_otp(identifier, code, redis, *, namespace):
        assert code == sent["code"]
        return None

    async def _fake_consume(identifier, redis, *, namespace):
        return None

    import app.api.seller_phone_change as mod
    monkeypatch.setattr(mod, "request_otp", _fake_request_otp)
    monkeypatch.setattr(mod, "verify_otp", _fake_verify_otp)
    monkeypatch.setattr(mod, "consume_otp_key", _fake_consume)

    req = await client.post(
        "/api/v1/sellers/me/phone/otp/request", json={"phone": "+919811119999"}
    )
    assert req.status_code == 200, req.text
    ver = await client.post(
        "/api/v1/sellers/me/phone/otp/verify",
        json={"phone": "+919811119999", "code": "123456"},
    )
    assert ver.status_code == 200, ver.text
    assert ver.json()["phone_change_token"]


@pytest.mark.asyncio
async def test_create_identity_cr_without_token_via_api_422(
    _seller_auth: dict, client: AsyncClient
) -> None:
    res = await client.post(
        "/api/v1/sellers/me/change-requests",
        json={
            "group": "identity",
            "proposed": {
                "full_name": "Ravi Sharma",
                "business_name": "Sharma General Store",
                "phone": "+919811119999",
            },
        },
    )
    assert res.status_code == 422, res.text
    assert res.json()["detail"] == "phone_verification_required"


@pytest.mark.asyncio
async def test_create_identity_cr_with_token_via_api_201(
    _seller_auth: dict, client: AsyncClient
) -> None:
    from app.core.security import create_seller_phone_change_token
    profile = _seller_auth["profile"]
    new_phone = "+919811119999"
    token = create_seller_phone_change_token(profile.user_id, new_phone)
    res = await client.post(
        "/api/v1/sellers/me/change-requests",
        json={
            "group": "identity",
            "proposed": {
                "full_name": "Ravi Sharma",
                "business_name": "Sharma General Store",
                "phone": new_phone,
            },
            "phone_change_token": token,
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "submitted"
