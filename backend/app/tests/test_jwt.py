"""JWT round-trip, tampered signature, expiry, and role-claim tests."""
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token
from app.models.base import User, UserRole


@pytest.fixture(autouse=True)
async def setup_test_db() -> AsyncGenerator[None, None]:
    """No-op override — JWT tests need no database."""
    yield


def _make_user(role: UserRole = UserRole.Customer) -> User:
    user = User(email="test@example.com", role=role, full_name="Test User")
    user.id = 42
    return user


def test_create_and_decode_round_trip() -> None:
    user = _make_user()
    token = create_access_token(user)
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == UserRole.Customer.value


def test_role_claim_matches_user_role() -> None:
    for role in UserRole:
        token = create_access_token(_make_user(role))
        payload = decode_access_token(token)
        assert payload["role"] == role.value


def test_tampered_signature_rejected() -> None:
    from fastapi import HTTPException

    user = _make_user()
    token = create_access_token(user)
    # Flip one character in the signature segment
    parts = token.split(".")
    sig = parts[2]
    parts[2] = sig[:-1] + ("A" if sig[-1] != "A" else "B")
    bad_token = ".".join(parts)

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(bad_token)
    assert exc_info.value.status_code == 401


def test_expired_token_rejected() -> None:
    from fastapi import HTTPException

    user = _make_user()
    past = datetime.now(timezone.utc) - timedelta(hours=25)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "iat": past,
        "exp": past + timedelta(hours=1),
    }
    expired_token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(expired_token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_wrong_secret_rejected() -> None:
    from fastapi import HTTPException

    token = jwt.encode(
        {"sub": "42", "role": "customer", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "wrong-secret",
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)
    assert exc_info.value.status_code == 401
