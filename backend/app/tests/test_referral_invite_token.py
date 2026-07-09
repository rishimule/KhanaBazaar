# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from fastapi import HTTPException

from app.core.security import (
    create_referral_invite_token,
    decode_referral_invite_token,
)


def test_roundtrip():
    tok = create_referral_invite_token(
        referral_id=5, target_role="customer", email="a@b.com", phone=None, expires_days=14
    )
    claims = decode_referral_invite_token(tok)
    assert claims["referral_id"] == 5
    assert claims["target_role"] == "customer"
    assert claims["email"] == "a@b.com"
    assert claims["phone"] is None


def test_rejects_wrong_type():
    from app.core.security import create_seller_signup_token

    tok = create_seller_signup_token("a@b.com", "+919812345678")
    with pytest.raises(HTTPException) as ei:
        decode_referral_invite_token(tok)
    assert ei.value.status_code == 400


def test_rejects_garbage():
    with pytest.raises(HTTPException) as ei:
        decode_referral_invite_token("not-a-jwt")
    assert ei.value.status_code == 400
