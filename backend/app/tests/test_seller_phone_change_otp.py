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
