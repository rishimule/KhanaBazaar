# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Customer signup collects a verified phone (spec 2026-10-08).

Covers the pre-account endpoints `/auth/customer/phone/otp/{request,verify}`,
their budgets, and the account-creation rules in `/auth/otp/verify`. Referral
activation is covered in test_referral_activation.py.
"""
import asyncio
import re
from collections.abc import Generator
from typing import Any

import pytest
import redis.asyncio as aioredis
from fakeredis.aioredis import FakeRedis
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.config import settings
from app.core.otp import RateLimited, enforce_distinct_hourly_budget, hash_code
from app.core.redis import get_redis
from app.core.security import (
    create_customer_signup_phone_token,
    decode_customer_signup_phone_token,
)
from app.core.sms import get_sms_sender
from app.core.whatsapp import get_whatsapp_sender
from app.core.whatsapp_templates import TEMPLATES, WhatsAppTemplate
from app.models.address import Address
from app.models.base import AccountStatus, User, UserRole
from app.models.profile import CustomerProfile, SellerProfile
from app.services.customer_signup import budget_identity
from tests._helpers import make_address

EMAIL = "newbuyer@example.com"
EMAIL_CODE = "246810"
PHONE = "+919876501234"


class _RecordingSMS:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, to: str, text: str) -> None:
        self.sent.append((to, text))


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis(decode_responses=True)


@pytest.fixture
def sms() -> _RecordingSMS:
    return _RecordingSMS()


@pytest.fixture(autouse=True)
def _overrides(
    fake_redis: FakeRedis, sms: _RecordingSMS
) -> Generator[None, None, None]:
    """Pin Redis and SMS for this module, then put conftest's own overrides
    back. Popping them instead would leak the real Redis into later tests."""
    saved = {dep: app.dependency_overrides.get(dep) for dep in (get_redis, get_sms_sender)}
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_sms_sender] = lambda: sms
    yield
    for dep, prev in saved.items():
        if prev is None:
            app.dependency_overrides.pop(dep, None)
        else:
            app.dependency_overrides[dep] = prev


@pytest.fixture
def otp_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PHONE_OTP_ENABLED", False)


async def _seed_email_code(
    redis: FakeRedis, email: str = EMAIL, code: str = EMAIL_CODE
) -> None:
    """Store a live login code exactly as /auth/otp/request would."""
    key = f"otp:email:code:{email}"
    await redis.hset(key, mapping={"code_hash": hash_code(code), "attempts": "0"})  # type: ignore[misc]
    await redis.expire(key, 600)


def _sent_code(sms: _RecordingSMS) -> str:
    match = re.search(r"\b(\d{6})\b", sms.sent[-1][1])
    assert match, sms.sent
    return match.group(1)


async def _request(
    client: AsyncClient,
    *,
    email: str = EMAIL,
    email_code: str = EMAIL_CODE,
    phone: str = PHONE,
) -> Any:
    return await client.post(
        "/api/v1/auth/customer/phone/otp/request",
        json={"email": email, "email_code": email_code, "phone": phone},
    )


async def _verify(
    client: AsyncClient, *, code: str, email: str = EMAIL, phone: str = PHONE
) -> Any:
    return await client.post(
        "/api/v1/auth/customer/phone/otp/verify",
        json={"email": email, "phone": phone, "code": code},
    )


async def _add_customer(
    session: AsyncSession, *, email: str, phone: str | None
) -> None:
    user = User(email=email, role=UserRole.Customer)
    session.add(user)
    await session.flush()
    assert user.id is not None
    session.add(CustomerProfile(user_id=user.id, first_name="Held", phone=phone))
    await session.commit()


# ── budget helpers ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("email", "identity"),
    [
        ("plain@example.com", "plain@example.com"),
        ("a.b+promo@example.com", "a.b@example.com"),
        ("A.B+promo@GMail.com", "ab@gmail.com"),
        ("a.b@googlemail.com", "ab@gmail.com"),
    ],
)
def test_budget_identity_folds_trivial_variants(email: str, identity: str) -> None:
    assert budget_identity(email) == identity


async def test_distinct_budget_counts_members_not_calls(fake_redis: FakeRedis) -> None:
    for i in range(settings.OTP_MAX_PER_HOUR):
        await enforce_distinct_hourly_budget("who", f"m{i}", fake_redis, namespace="t")
    # A member already counted stays free, even with the set full.
    await enforce_distinct_hourly_budget("who", "m0", fake_redis, namespace="t")
    with pytest.raises(RateLimited) as exc:
        await enforce_distinct_hourly_budget("who", "new", fake_redis, namespace="t")
    assert exc.value.retry_after > 0
    assert 0 < await fake_redis.ttl("otp:t:distinct:who") <= 3600


async def test_distinct_budget_holds_under_a_concurrent_burst() -> None:
    """Concurrent first-time members must not overshoot the cap. This uses the
    real Redis server: its round trips yield to the event loop and interleave,
    where FakeRedis never does — a check-then-add would pass on FakeRedis and
    let a whole burst through in production."""
    real = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    key = "otp:test_burst:distinct:burst@example.com"
    try:
        await real.delete(key)

        async def one(i: int) -> bool:
            try:
                await enforce_distinct_hourly_budget(
                    "burst@example.com", f"+91980000{i:04d}", real, namespace="test_burst"
                )
                return True
            except RateLimited:
                return False

        results = await asyncio.gather(*(one(i) for i in range(20)))
        assert sum(results) == settings.OTP_MAX_PER_HOUR
        assert await real.scard(key) == settings.OTP_MAX_PER_HOUR  # type: ignore[misc]
        assert 0 < await real.ttl(key) <= 3600
        # A member already counted stays free once the set is full.
        assert await one(next(i for i, ok in enumerate(results) if ok))
    finally:
        await real.delete(key)
        await real.aclose()


async def test_distinct_budget_window_is_fixed_not_sliding(
    fake_redis: FakeRedis,
) -> None:
    await enforce_distinct_hourly_budget("who", "m0", fake_redis, namespace="t")
    await fake_redis.expire("otp:t:distinct:who", 100)
    await enforce_distinct_hourly_budget("who", "m1", fake_redis, namespace="t")
    assert await fake_redis.ttl("otp:t:distinct:who") <= 100


# ── request ─────────────────────────────────────────────────────────────


async def test_request_flag_off_returns_token_and_sends_nothing(
    client: AsyncClient, fake_redis: FakeRedis, sms: _RecordingSMS, otp_disabled: None
) -> None:
    await _seed_email_code(fake_redis)
    resp = await _request(client, phone="+91 98765-01234")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["otp_required"] is False
    assert sms.sent == []
    assert decode_customer_signup_phone_token(body["phone_token"]) == (
        EMAIL,
        PHONE,
        False,
    )


async def test_request_flag_on_sends_a_code_and_no_token(
    client: AsyncClient, fake_redis: FakeRedis, sms: _RecordingSMS
) -> None:
    await _seed_email_code(fake_redis)
    resp = await _request(client)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "ok": True,
        "otp_required": True,
        "expires_in": settings.OTP_TTL_SECONDS,
    }
    assert len(sms.sent) == 1
    assert sms.sent[0][0] == PHONE


async def test_request_prefers_whatsapp_when_enabled(
    client: AsyncClient, fake_redis: FakeRedis, sms: _RecordingSMS
) -> None:
    sent: list[tuple[str, str]] = []

    class _WhatsApp:
        async def send_template(
            self, to: str, template: WhatsAppTemplate, variables: dict[str, str]
        ) -> None:
            sent.append((to, template.name))

    app.dependency_overrides[get_whatsapp_sender] = lambda: _WhatsApp()
    try:
        await _seed_email_code(fake_redis)
        assert (await _request(client)).status_code == 200
    finally:
        app.dependency_overrides.pop(get_whatsapp_sender, None)
    assert sent == [(PHONE, "otp_customer_signup")]
    assert sms.sent == []


async def test_request_does_not_consume_the_email_code(
    client: AsyncClient, fake_redis: FakeRedis, otp_disabled: None
) -> None:
    await _seed_email_code(fake_redis)
    assert (await _request(client)).status_code == 200
    assert await fake_redis.exists(f"otp:email:code:{EMAIL}") == 1


@pytest.mark.parametrize(
    ("seed", "email_code", "status", "error"),
    [
        (True, "000000", 400, "invalid_code"),
        (False, EMAIL_CODE, 410, "code_expired_or_used"),
    ],
)
async def test_request_requires_the_live_email_code(
    client: AsyncClient,
    fake_redis: FakeRedis,
    sms: _RecordingSMS,
    seed: bool,
    email_code: str,
    status: int,
    error: str,
) -> None:
    if seed:
        await _seed_email_code(fake_redis)
    resp = await _request(client, email_code=email_code)
    assert resp.status_code == status
    assert resp.json()["detail"]["error"] == error
    assert sms.sent == []


async def test_request_locks_after_too_many_wrong_email_codes(
    client: AsyncClient, fake_redis: FakeRedis
) -> None:
    await _seed_email_code(fake_redis)
    for _ in range(settings.OTP_MAX_ATTEMPTS - 1):
        assert (await _request(client, email_code="000000")).status_code == 400
    resp = await _request(client, email_code="000000")
    assert resp.status_code == 429
    assert resp.json()["detail"]["error"] == "too_many_attempts"


async def test_request_gate_runs_before_any_phone_check(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Without a live code nothing about the number leaks, taken or not."""
    await _add_customer(session, email="holder@example.com", phone=PHONE)
    resp = await _request(client)
    assert resp.status_code == 410


async def test_request_rejects_a_registered_email(
    client: AsyncClient, fake_redis: FakeRedis, session: AsyncSession, sms: _RecordingSMS
) -> None:
    await _add_customer(session, email=EMAIL, phone=None)
    await _seed_email_code(fake_redis)
    resp = await _request(client)
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "email_already_registered"
    assert sms.sent == []


@pytest.mark.parametrize(
    "phone",
    ["9876501234", "+91 12345 67890", "+9198765012", "+919" + "८" * 9, ""],
)
async def test_request_rejects_an_invalid_phone(
    client: AsyncClient, fake_redis: FakeRedis, phone: str
) -> None:
    await _seed_email_code(fake_redis)
    resp = await _request(client, phone=phone)
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_phone"


async def test_invalid_phones_are_not_charged_to_the_breadth_cap(
    client: AsyncClient, fake_redis: FakeRedis, otp_disabled: None
) -> None:
    await _seed_email_code(fake_redis)
    for i in range(settings.OTP_MAX_PER_HOUR + 2):
        assert (await _request(client, phone=f"1234{i}")).status_code == 400
    assert (await _request(client)).status_code == 200


async def test_request_rejects_a_number_another_customer_holds(
    client: AsyncClient, fake_redis: FakeRedis, session: AsyncSession, sms: _RecordingSMS
) -> None:
    await _add_customer(session, email="holder@example.com", phone=PHONE)
    await _seed_email_code(fake_redis)
    resp = await _request(client)
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "phone_already_in_use"
    assert sms.sent == []


async def test_request_allows_a_number_a_seller_holds(
    client: AsyncClient, fake_redis: FakeRedis, session: AsyncSession, otp_disabled: None
) -> None:
    """Uniqueness is per role, as in the profile phone flow."""
    user = User(email="seller@example.com", role=UserRole.Seller)
    session.add(user)
    await session.flush()
    address = Address(**make_address())
    session.add(address)
    await session.flush()
    assert user.id is not None and address.id is not None
    session.add(
        SellerProfile(
            user_id=user.id,
            first_name="S",
            business_name="Shop",
            phone=PHONE,
            business_address_id=address.id,
        )
    )
    await session.commit()
    await _seed_email_code(fake_redis)
    assert (await _request(client)).status_code == 200


async def test_taken_number_probes_are_charged_to_the_breadth_cap(
    client: AsyncClient, fake_redis: FakeRedis, session: AsyncSession, otp_disabled: None
) -> None:
    for i in range(settings.OTP_MAX_PER_HOUR):
        await _add_customer(session, email=f"holder{i}@example.com", phone=f"+91987650{i:04d}")
    await _seed_email_code(fake_redis)
    for i in range(settings.OTP_MAX_PER_HOUR):
        assert (await _request(client, phone=f"+91987650{i:04d}")).status_code == 409
    resp = await _request(client, phone="+919876509999")
    assert resp.status_code == 429
    assert resp.json()["detail"]["error"] == "rate_limited"


async def test_breadth_cap_counts_distinct_numbers(
    client: AsyncClient, fake_redis: FakeRedis, otp_disabled: None
) -> None:
    await _seed_email_code(fake_redis)
    # Re-asking for one number is free for the breadth cap…
    for _ in range(3):
        assert (await _request(client)).status_code == 200
    # …so four more numbers still fit (5 distinct in total).
    for i in range(1, settings.OTP_MAX_PER_HOUR):
        assert (await _request(client, phone=f"+91987650{i:04d}")).status_code == 200
    resp = await _request(client, phone="+919876509999")
    assert resp.status_code == 429
    assert resp.json()["detail"]["retry_after"] > 0


async def test_plus_tag_and_gmail_dot_variants_share_the_breadth_cap(
    client: AsyncClient, fake_redis: FakeRedis, otp_disabled: None
) -> None:
    variants = [
        "buyer@gmail.com",
        "buyer+1@gmail.com",
        "b.uyer@gmail.com",
        "bu.yer+x@googlemail.com",
        "buyer+2@gmail.com",
    ]
    for i, email in enumerate(variants):
        await _seed_email_code(fake_redis, email=email)
        resp = await _request(client, email=email, phone=f"+91987650{i:04d}")
        assert resp.status_code == 200, (email, resp.text)
    await _seed_email_code(fake_redis, email="b.u.y.e.r+3@gmail.com")
    resp = await _request(client, email="b.u.y.e.r+3@gmail.com", phone="+919876509999")
    assert resp.status_code == 429


@pytest.mark.parametrize("otp_on", [True, False])
async def test_per_phone_budget_holds_across_emails(
    client: AsyncClient,
    fake_redis: FakeRedis,
    sms: _RecordingSMS,
    monkeypatch: pytest.MonkeyPatch,
    otp_on: bool,
) -> None:
    """Nobody texts (or, with OTP off, probes) one number more than the
    hourly allowance, however many inboxes they use."""
    monkeypatch.setattr(settings, "PHONE_OTP_ENABLED", otp_on)
    for i in range(settings.OTP_MAX_PER_HOUR):
        email = f"buyer{i}@example.com"
        await _seed_email_code(fake_redis, email=email)
        assert (await _request(client, email=email)).status_code == 200
    await _seed_email_code(fake_redis, email="one-more@example.com")
    resp = await _request(client, email="one-more@example.com")
    assert resp.status_code == 429
    assert resp.json()["detail"]["error"] == "rate_limited"
    assert len(sms.sent) == (settings.OTP_MAX_PER_HOUR if otp_on else 0)


async def test_cooldown_taps_do_not_spend_the_per_phone_budget(
    client: AsyncClient, fake_redis: FakeRedis, sms: _RecordingSMS
) -> None:
    """Only real sends spend a number's hourly allowance: a flaky network
    that makes the customer tap again must not lock the number for an hour."""
    await _seed_email_code(fake_redis)
    assert (await _request(client)).status_code == 200
    for _ in range(settings.OTP_MAX_PER_HOUR + 1):
        resp = await _request(client)
        assert resp.status_code == 429
        detail = resp.json()["detail"]
        assert detail["error"] == "rate_limited"
        assert 0 < detail["retry_after"] <= settings.OTP_RESEND_COOLDOWN
        # Lets a client that lost the first response go to the code step.
        assert detail["code_sent"] is True
    assert await fake_redis.get(f"otp:customer_signup_phone:hourly:{PHONE}") == "1"
    assert len(sms.sent) == 1


async def test_flag_on_resend_inside_the_cooldown_is_rate_limited(
    client: AsyncClient, fake_redis: FakeRedis, sms: _RecordingSMS
) -> None:
    await _seed_email_code(fake_redis)
    assert (await _request(client)).status_code == 200
    resp = await _request(client)
    assert resp.status_code == 429
    assert resp.json()["detail"]["retry_after"] > 0
    assert len(sms.sent) == 1


def test_otp_customer_signup_template_is_registered() -> None:
    template = TEMPLATES["otp_customer_signup"]
    assert template.category == "AUTHENTICATION"
    assert template.variables == ("code",)
    assert "123456" in template.render({"code": "123456"})


# ── verify ──────────────────────────────────────────────────────────────


async def test_verify_trades_the_code_for_a_token_once(
    client: AsyncClient, fake_redis: FakeRedis, sms: _RecordingSMS
) -> None:
    await _seed_email_code(fake_redis)
    assert (await _request(client)).status_code == 200
    code = _sent_code(sms)
    resp = await _verify(client, code=code)
    assert resp.status_code == 200, resp.text
    assert decode_customer_signup_phone_token(resp.json()["phone_token"]) == (
        EMAIL,
        PHONE,
        True,
    )
    again = await _verify(client, code=code)
    assert again.status_code == 410
    assert again.json()["detail"]["error"] == "code_expired_or_used"


async def test_verify_rejects_a_wrong_code_then_locks(
    client: AsyncClient, fake_redis: FakeRedis, sms: _RecordingSMS
) -> None:
    await _seed_email_code(fake_redis)
    assert (await _request(client)).status_code == 200
    for _ in range(settings.OTP_MAX_ATTEMPTS - 1):
        resp = await _verify(client, code="000000")
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "invalid_code"
    resp = await _verify(client, code="000000")
    assert resp.status_code == 429
    assert resp.json()["detail"]["error"] == "too_many_attempts"


async def test_another_email_cannot_use_or_burn_someone_elses_code(
    client: AsyncClient, fake_redis: FakeRedis, sms: _RecordingSMS
) -> None:
    """The code is keyed by phone + requesting email (spec §4.2)."""
    await _seed_email_code(fake_redis)
    assert (await _request(client)).status_code == 200
    code = _sent_code(sms)
    for _ in range(settings.OTP_MAX_ATTEMPTS + 1):
        resp = await _verify(client, code="000000", email="stranger@example.com")
        assert resp.status_code == 410
    assert (await _verify(client, code=code, email="stranger@example.com")).status_code == 410
    assert (await _verify(client, code=code)).status_code == 200


async def test_verify_never_mints_without_a_code_even_with_otp_off(
    client: AsyncClient, otp_disabled: None
) -> None:
    """The deliberate difference from the older chains (spec §4.3)."""
    resp = await _verify(client, code="123456")
    assert resp.status_code == 410
    assert resp.json()["detail"]["error"] == "code_expired_or_used"


async def test_code_sent_before_the_flag_flipped_off_still_verifies(
    client: AsyncClient,
    fake_redis: FakeRedis,
    sms: _RecordingSMS,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_email_code(fake_redis)
    assert (await _request(client)).status_code == 200
    monkeypatch.setattr(settings, "PHONE_OTP_ENABLED", False)
    resp = await _verify(client, code=_sent_code(sms))
    assert resp.status_code == 200, resp.text


async def test_verify_rejects_an_invalid_phone(client: AsyncClient) -> None:
    resp = await _verify(client, code="123456", phone="12345")
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_phone"


# ── account creation: /auth/otp/verify ──────────────────────────────────


async def _new_account(
    client: AsyncClient, *, phone_token: str | None = None, email: str = EMAIL
) -> Any:
    body: dict[str, object] = {
        "email": email,
        "code": EMAIL_CODE,
        "full_name": "Asha Rao",
        "accept_policies": True,
    }
    if phone_token is not None:
        body["phone_token"] = phone_token
    return await client.post("/api/v1/auth/otp/verify", json=body)


async def test_signup_end_to_end_with_phone_otp_off(
    client: AsyncClient,
    fake_redis: FakeRedis,
    session: AsyncSession,
    sms: _RecordingSMS,
    otp_disabled: None,
) -> None:
    await _seed_email_code(fake_redis)
    first = await client.post(
        "/api/v1/auth/otp/verify", json={"email": EMAIL, "code": EMAIL_CODE}
    )
    assert first.json()["needs_name"] is True
    token = (await _request(client)).json()["phone_token"]
    resp = await _new_account(client, phone_token=token)
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["role"] == "customer"
    profile = (await session.exec(select(CustomerProfile))).one()
    assert profile.phone == PHONE
    assert profile.phone_verified_at is not None
    assert sms.sent == []


async def test_signup_end_to_end_with_phone_otp_on(
    client: AsyncClient, fake_redis: FakeRedis, session: AsyncSession, sms: _RecordingSMS
) -> None:
    await _seed_email_code(fake_redis)
    assert (await _request(client)).json()["otp_required"] is True
    verified = await _verify(client, code=_sent_code(sms))
    resp = await _new_account(client, phone_token=verified.json()["phone_token"])
    assert resp.status_code == 200, resp.text
    profile = (await session.exec(select(CustomerProfile))).one()
    assert profile.phone == PHONE
    assert profile.phone_verified_at is not None


async def test_trust_token_is_refused_once_phone_otp_is_on(
    client: AsyncClient,
    fake_redis: FakeRedis,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A number taken on trust before the flag flipped on must be proven like
    any other: otherwise an account stamped after the cutover would carry an
    unproven "verified" number (spec §4.1)."""
    monkeypatch.setattr(settings, "PHONE_OTP_ENABLED", False)
    await _seed_email_code(fake_redis)
    token = (await _request(client)).json()["phone_token"]
    monkeypatch.setattr(settings, "PHONE_OTP_ENABLED", True)
    resp = await _new_account(client, phone_token=token)
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_phone_token"
    assert (await session.exec(select(User))).first() is None


async def test_signup_without_a_phone_token_is_refused(
    client: AsyncClient, fake_redis: FakeRedis, session: AsyncSession
) -> None:
    await _seed_email_code(fake_redis)
    resp = await _new_account(client)
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "phone_required"
    assert (await session.exec(select(User))).first() is None


async def test_signup_rejects_a_token_minted_for_another_email(
    client: AsyncClient, fake_redis: FakeRedis
) -> None:
    await _seed_email_code(fake_redis)
    token = create_customer_signup_phone_token("other@example.com", PHONE, proven=True)
    resp = await _new_account(client, phone_token=token)
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_phone_token"


async def test_signup_rejects_garbage_and_wrong_type_tokens(
    client: AsyncClient, fake_redis: FakeRedis
) -> None:
    from app.core.security import create_seller_signup_token

    await _seed_email_code(fake_redis)
    for token in ("garbage", create_seller_signup_token(EMAIL, PHONE)):
        resp = await _new_account(client, phone_token=token)
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "invalid_phone_token"


async def test_signup_with_an_expired_token_is_410(
    client: AsyncClient, fake_redis: FakeRedis
) -> None:
    from datetime import datetime, timedelta, timezone

    import jwt

    await _seed_email_code(fake_redis)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "email": EMAIL,
            "phone": PHONE,
            "type": "customer_signup_phone",
            "iat": now - timedelta(minutes=20),
            "exp": now - timedelta(minutes=10),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    resp = await _new_account(client, phone_token=token)
    assert resp.status_code == 410
    assert resp.json()["detail"]["error"] == "phone_token_expired"


async def test_number_claimed_after_the_token_is_a_409_and_retry_works(
    client: AsyncClient, fake_redis: FakeRedis, session: AsyncSession
) -> None:
    await _seed_email_code(fake_redis)
    token = create_customer_signup_phone_token(EMAIL, PHONE, proven=True)
    await _add_customer(session, email="fast@example.com", phone=PHONE)
    resp = await _new_account(client, phone_token=token)
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "phone_already_in_use"
    # The email code survives the 409: another number goes straight through.
    retry = await _new_account(
        client, phone_token=create_customer_signup_phone_token(EMAIL, "+919876509876", proven=True)
    )
    assert retry.status_code == 200, retry.text


async def test_phone_unique_race_is_a_409_not_a_500(
    client: AsyncClient,
    fake_redis: FakeRedis,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pre-check can pass and still lose to a concurrent insert: a clean
    409, not a 500. Policies are published so record_acceptance runs too."""
    from app.models.consent import PolicyDocument, PolicyKind

    session.add(PolicyDocument(kind=PolicyKind.terms, version=1, body="t"))
    session.add(PolicyDocument(kind=PolicyKind.privacy, version=1, body="p"))
    await session.commit()

    from app.services import customer_signup

    calls = 0

    async def _free_then_real(s: AsyncSession, p: str) -> bool:
        # The pre-check runs before the racing insert lands; the check that
        # names the loser after the rollback sees the committed winner.
        nonlocal calls
        calls += 1
        if calls == 1:
            return False
        return await customer_signup.customer_phone_taken(s, p)

    monkeypatch.setattr("app.api.auth.customer_phone_taken", _free_then_real)
    await _add_customer(session, email="fast@example.com", phone=PHONE)
    await _seed_email_code(fake_redis)
    resp = await _new_account(
        client, phone_token=create_customer_signup_phone_token(EMAIL, PHONE, proven=True)
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["error"] == "phone_already_in_use"
    assert (
        await session.exec(select(User).where(User.email == EMAIL))
    ).first() is None


async def test_same_email_race_is_email_already_registered(
    client: AsyncClient,
    fake_redis: FakeRedis,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two tabs, one email: the loser gets a clean 409 instead of a 500."""

    async def _other_tab_wins(_session: AsyncSession, _phone: str) -> bool:
        session.add(User(email=EMAIL, role=UserRole.Customer))
        await session.commit()
        return False

    monkeypatch.setattr("app.api.auth.customer_phone_taken", _other_tab_wins)
    await _seed_email_code(fake_redis)
    resp = await _new_account(
        client, phone_token=create_customer_signup_phone_token(EMAIL, PHONE, proven=True)
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["error"] == "email_already_registered"


async def test_existing_customer_login_ignores_a_phone_token(
    client: AsyncClient, fake_redis: FakeRedis, session: AsyncSession
) -> None:
    await _add_customer(session, email=EMAIL, phone=None)
    await _seed_email_code(fake_redis)
    resp = await client.post(
        "/api/v1/auth/otp/verify",
        json={
            "email": EMAIL,
            "code": EMAIL_CODE,
            "phone_token": create_customer_signup_phone_token(EMAIL, PHONE, proven=True),
        },
    )
    assert resp.status_code == 200, resp.text
    profile = (await session.exec(select(CustomerProfile))).one()
    await session.refresh(profile)
    assert profile.phone is None


async def test_gate_runs_before_the_registered_email_check(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Without a live code a caller can't tell registered emails apart."""
    await _add_customer(session, email=EMAIL, phone=None)
    resp = await _request(client)
    assert resp.status_code == 410
    assert resp.json()["detail"]["error"] == "code_expired_or_used"


async def test_tokens_bind_the_normalized_email(
    client: AsyncClient, fake_redis: FakeRedis, sms: _RecordingSMS
) -> None:
    await _seed_email_code(fake_redis)
    assert (await _request(client, email="NewBuyer@Example.COM")).status_code == 200
    resp = await _verify(client, code=_sent_code(sms), email="NewBuyer@Example.COM")
    assert resp.status_code == 200, resp.text
    assert decode_customer_signup_phone_token(resp.json()["phone_token"])[0] == EMAIL


async def test_a_deleted_account_still_holds_its_number(
    client: AsyncClient, fake_redis: FakeRedis, session: AsyncSession
) -> None:
    """Accounts are never scrubbed, so a deleted customer's number stays
    taken (spec §9)."""
    user = User(
        email="gone@example.com",
        role=UserRole.Customer,
        account_status=AccountStatus.deleted,
        is_active=False,
    )
    session.add(user)
    await session.flush()
    assert user.id is not None
    session.add(CustomerProfile(user_id=user.id, first_name="Gone", phone=PHONE))
    await session.commit()
    await _seed_email_code(fake_redis)
    resp = await _request(client)
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "phone_already_in_use"


async def test_an_unrelated_integrity_error_is_not_relabelled(
    client: AsyncClient, fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The backstop names an email or phone race; anything else surfaces."""

    async def _boom(_s: AsyncSession, _uid: int) -> None:
        raise IntegrityError("INSERT", {}, Exception("uq_something_else"))

    monkeypatch.setattr("app.api.auth.record_acceptance", _boom)
    await _seed_email_code(fake_redis)
    with pytest.raises(IntegrityError):
        await _new_account(
            client, phone_token=create_customer_signup_phone_token(EMAIL, PHONE, proven=True)
        )
