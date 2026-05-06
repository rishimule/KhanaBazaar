"""Tests for the seller email-stage and signup-stage JWT helpers."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import (
    create_seller_email_token,
    create_seller_signup_token,
    decode_seller_email_token,
    decode_seller_signup_token,
)


def test_email_token_round_trip():
    tok = create_seller_email_token("seller@test.com")
    assert decode_seller_email_token(tok) == "seller@test.com"


def test_signup_token_round_trip():
    tok = create_seller_signup_token("seller@test.com", "+919876543210")
    email, phone = decode_seller_signup_token(tok)
    assert email == "seller@test.com"
    assert phone == "+919876543210"


def test_email_token_rejected_when_used_as_signup_token():
    tok = create_seller_email_token("seller@test.com")
    with pytest.raises(HTTPException) as exc:
        decode_seller_signup_token(tok)
    assert exc.value.status_code == 400


def test_signup_token_rejected_when_used_as_email_token():
    tok = create_seller_signup_token("seller@test.com", "+919876543210")
    with pytest.raises(HTTPException) as exc:
        decode_seller_email_token(tok)
    assert exc.value.status_code == 400


def test_expired_signup_token_rejected():
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


def test_invalid_signup_token_rejected():
    with pytest.raises(HTTPException) as exc:
        decode_seller_signup_token("not-a-jwt")
    assert exc.value.status_code == 400
