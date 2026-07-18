# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timezone

from app.core.security import create_access_token, decode_access_token
from app.models.base import User, UserRole


def test_access_token_carries_sid_and_short_exp() -> None:
    user = User(id=42, email="t@x.test", role=UserRole.Customer)
    token = create_access_token(user, sid=7)
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["sid"] == 7
    exp = datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc)  # type: ignore[arg-type]
    iat = datetime.fromtimestamp(int(payload["iat"]), tz=timezone.utc)  # type: ignore[arg-type]
    minutes = (exp - iat).total_seconds() / 60
    assert 14 <= minutes <= 16


def test_access_token_without_sid_still_valid() -> None:
    user = User(id=43, email="t2@x.test", role=UserRole.Customer)
    token = create_access_token(user)
    payload = decode_access_token(token)
    assert payload["sub"] == "43"
    assert "sid" not in payload
