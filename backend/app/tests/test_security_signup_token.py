# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Tests for the seller email/signup-stage and customer signup-phone JWT
helpers."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import (
    create_customer_signup_phone_token,
    create_seller_email_token,
    create_seller_signup_token,
    decode_customer_signup_phone_token,
    decode_seller_email_token,
    decode_seller_signup_token,
)


def test_email_token_round_trip() -> None:
    tok = create_seller_email_token("seller@test.com")
    assert decode_seller_email_token(tok) == "seller@test.com"


def test_signup_token_round_trip() -> None:
    tok = create_seller_signup_token("seller@test.com", "+919876543210")
    email, phone = decode_seller_signup_token(tok)
    assert email == "seller@test.com"
    assert phone == "+919876543210"


def test_email_token_rejected_when_used_as_signup_token() -> None:
    tok = create_seller_email_token("seller@test.com")
    with pytest.raises(HTTPException) as exc:
        decode_seller_signup_token(tok)
    assert exc.value.status_code == 400


def test_signup_token_rejected_when_used_as_email_token() -> None:
    tok = create_seller_signup_token("seller@test.com", "+919876543210")
    with pytest.raises(HTTPException) as exc:
        decode_seller_email_token(tok)
    assert exc.value.status_code == 400


def test_expired_signup_token_rejected() -> None:
    payload = {
        "sub": "seller@test.com",
        "phone": "+919876543210",
        "type": "seller_signup",
        "iat": datetime.now(timezone.utc) - timedelta(minutes=20),
        "exp": datetime.now(timezone.utc) - timedelta(minutes=10),
    }
    expired = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        decode_seller_signup_token(expired)
    assert exc.value.status_code == 410


def test_invalid_signup_token_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        decode_seller_signup_token("not-a-jwt")
    assert exc.value.status_code == 400


# ── Customer signup phone token ─────────────────────────────────────────


def test_customer_signup_phone_token_round_trip() -> None:
    tok = create_customer_signup_phone_token(
        "buyer@test.com", "+919876543210", proven=True
    )
    assert decode_customer_signup_phone_token(tok) == (
        "buyer@test.com",
        "+919876543210",
        True,
    )


def test_customer_signup_phone_token_has_no_sub_claim() -> None:
    """get_current_user loads a user by `sub`; without one this token can
    never pass for a login."""
    tok = create_customer_signup_phone_token(
        "buyer@test.com", "+919876543210", proven=True
    )
    claims = jwt.decode(tok, settings.JWT_SECRET, algorithms=["HS256"])
    assert "sub" not in claims
    assert claims["type"] == "customer_signup_phone"
    assert claims["email"] == "buyer@test.com"


def test_customer_signup_phone_token_tolerates_small_clock_skew() -> None:
    """Minted by an instance whose clock runs a few seconds ahead."""
    now = datetime.now(timezone.utc)
    tok = jwt.encode(
        {
            "email": "buyer@test.com",
            "phone": "+919876543210",
            "type": "customer_signup_phone",
            "proven": True,
            "iat": now + timedelta(seconds=10),
            "exp": now + timedelta(minutes=10),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    assert decode_customer_signup_phone_token(tok) == (
        "buyer@test.com",
        "+919876543210",
        True,
    )


def test_trust_token_records_that_the_number_was_not_proven() -> None:
    tok = create_customer_signup_phone_token(
        "buyer@test.com", "+919876543210", proven=False
    )
    assert decode_customer_signup_phone_token(tok)[2] is False


def test_referral_invite_token_rejected_as_customer_signup_phone_token() -> None:
    """An invite token carries `email` and `phone` claims too — only the type
    check keeps an invitee from passing their invite link off as proof of
    the referrer-typed number."""
    from app.core.security import create_referral_invite_token

    tok = create_referral_invite_token(
        referral_id=1,
        target_role="customer",
        email="buyer@test.com",
        phone="+919876543210",
        expires_days=14,
    )
    with pytest.raises(HTTPException) as exc:
        decode_customer_signup_phone_token(tok)
    detail: object = exc.value.detail
    assert exc.value.status_code == 400
    assert detail == {"error": "invalid_phone_token"}


def test_seller_signup_token_rejected_as_customer_signup_phone_token() -> None:
    tok = create_seller_signup_token("buyer@test.com", "+919876543210")
    with pytest.raises(HTTPException) as exc:
        decode_customer_signup_phone_token(tok)
    assert exc.value.status_code == 400
    detail: object = exc.value.detail
    assert detail == {"error": "invalid_phone_token"}


def test_expired_customer_signup_phone_token_is_410() -> None:
    now = datetime.now(timezone.utc)
    tok = jwt.encode(
        {
            "email": "buyer@test.com",
            "phone": "+919876543210",
            "type": "customer_signup_phone",
            "iat": now - timedelta(minutes=20),
            "exp": now - timedelta(minutes=10),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc:
        decode_customer_signup_phone_token(tok)
    assert exc.value.status_code == 410
    detail: object = exc.value.detail
    assert detail == {"error": "phone_token_expired"}


@pytest.mark.parametrize(
    "claims",
    [
        {"type": "customer_signup_phone", "phone": "+919876543210"},
        {"type": "customer_signup_phone", "email": "buyer@test.com"},
        {"type": "customer_signup_phone", "email": 5, "phone": "+919876543210"},
        {"type": "customer_signup_phone", "email": "b@t.com", "phone": "+919876543210"},
        {
            "type": "customer_signup_phone",
            "email": "b@t.com",
            "phone": "+919876543210",
            "proven": "yes",
        },
    ],
)
def test_customer_signup_phone_token_missing_claims_rejected(
    claims: dict[str, object],
) -> None:
    now = datetime.now(timezone.utc)
    tok = jwt.encode(
        {**claims, "iat": now, "exp": now + timedelta(minutes=5)},
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc:
        decode_customer_signup_phone_token(tok)
    assert exc.value.status_code == 400


def test_garbage_customer_signup_phone_token_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        decode_customer_signup_phone_token("not-a-jwt")
    assert exc.value.status_code == 400
