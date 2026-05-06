# Seller Signup Phone-OTP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate seller registration on a phone-OTP verification step in addition to the existing email-OTP step, with a sandbox SMS path (console) and a Twilio production path.

**Architecture:** Reuse the existing Redis-backed OTP primitives by parameterising them with a `namespace` argument. Replace the single-purpose `email_token` hand-off into `/auth/seller/register` with a combined `signup_token` whose claims bind both the verified email and verified phone. Dispatch SMS inline via a `SMSSender` factory that mirrors the existing `EmailSender`.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, Pydantic-Settings, redis-py async, PyJWT, httpx, pytest, Next.js App Router (React 19, TypeScript).

**Companion spec:** `docs/superpowers/specs/2026-05-05-seller-phone-otp-design.md`. Always re-read when context is unclear.

**Branch:** `feat/seller-phone-otp` (already created off `main`).

**Out of scope:** the resubmit flow (`?resubmit=true` in `seller/signup/page.tsx`). Resubmit uses an authenticated `PATCH /sellers/me/profile` path, not `/auth/seller/register`, and does not re-verify phone. This plan does not modify resubmit behaviour.

---

### Task 1: Add SMS-provider and Twilio settings to config

**Files:**
- Modify: `backend/app/src/app/core/config.py`
- Modify: `backend/app/.env.example` (if it exists; otherwise skip)
- Test: `backend/app/tests/test_config_sms.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# backend/app/tests/test_config_sms.py
import importlib

def test_sms_provider_defaults_to_console(monkeypatch):
    monkeypatch.delenv("SMS_PROVIDER", raising=False)
    import app.core.config as cfg
    importlib.reload(cfg)
    assert cfg.settings.SMS_PROVIDER == "console"


def test_sms_provider_accepts_twilio(monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "twilio")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok_test")
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+15005550006")
    import app.core.config as cfg
    importlib.reload(cfg)
    assert cfg.settings.SMS_PROVIDER == "twilio"
    assert cfg.settings.TWILIO_ACCOUNT_SID == "AC_test"
    assert cfg.settings.TWILIO_FROM_NUMBER == "+15005550006"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/app && uv run pytest tests/test_config_sms.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'SMS_PROVIDER'`.

- [ ] **Step 3: Add the settings**

Edit `backend/app/src/app/core/config.py`. Insert after the existing `RESEND_FROM_EMAIL: str = ""` line:

```python
    # SMS: "console" (dev/test) or "twilio" (production)
    SMS_PROVIDER: str = "console"
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""  # E.164, e.g. "+15005550006"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend/app && uv run pytest tests/test_config_sms.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run the full test suite as a regression check**

Run: `cd backend/app && uv run pytest -x -q`
Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/src/app/core/config.py backend/app/tests/test_config_sms.py
git commit -m "feat(config): add SMS_PROVIDER and Twilio settings"
```

---

### Task 2: Create the SMS sender module

**Files:**
- Create: `backend/app/src/app/core/sms.py`
- Test: `backend/app/tests/test_sms_sender.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# backend/app/tests/test_sms_sender.py
import pytest

from app.core.sms import (
    ConsoleSMSSender,
    TwilioSMSSender,
    get_sms_sender,
)


@pytest.mark.anyio
async def test_console_sender_does_not_raise(caplog):
    sender = ConsoleSMSSender()
    await sender.send(to="+919876543210", text="hello")
    # Should not raise; ConsoleSMSSender just logs.


def test_factory_returns_console_by_default(monkeypatch):
    from app.core import sms as sms_module
    sms_module.get_sms_sender.cache_clear()
    monkeypatch.setattr(sms_module.settings, "SMS_PROVIDER", "console")
    assert isinstance(sms_module.get_sms_sender(), ConsoleSMSSender)


def test_factory_returns_twilio_when_configured(monkeypatch):
    from app.core import sms as sms_module
    sms_module.get_sms_sender.cache_clear()
    monkeypatch.setattr(sms_module.settings, "SMS_PROVIDER", "twilio")
    assert isinstance(sms_module.get_sms_sender(), TwilioSMSSender)
```

(Add `pytest.ini` `asyncio_mode = auto` if not already set; the existing tests use the same convention.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/app && uv run pytest tests/test_sms_sender.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.sms'`.

- [ ] **Step 3: Create the sender module**

Create `backend/app/src/app/core/sms.py`:

```python
import logging
from functools import lru_cache
from typing import Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class SMSSender(Protocol):
    async def send(self, to: str, text: str) -> None: ...


class ConsoleSMSSender:
    async def send(self, to: str, text: str) -> None:
        logger.info("[SMS] to=%s\n%s", to, text)
        print(f"[SMS] to={to}\n{text}")


class TwilioSMSSender:
    async def send(self, to: str, text: str) -> None:
        url = (
            f"https://api.twilio.com/2010-04-01/Accounts/"
            f"{settings.TWILIO_ACCOUNT_SID}/Messages.json"
        )
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                data={
                    "From": settings.TWILIO_FROM_NUMBER,
                    "To": to,
                    "Body": text,
                },
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                timeout=10.0,
            )
            response.raise_for_status()


@lru_cache(maxsize=1)
def get_sms_sender() -> SMSSender:
    if settings.SMS_PROVIDER == "twilio":
        return TwilioSMSSender()
    return ConsoleSMSSender()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend/app && uv run pytest tests/test_sms_sender.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run lint + types**

Run: `cd backend/app && uv run ruff check app/core/sms.py && uv run mypy app/core/sms.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/src/app/core/sms.py backend/app/tests/test_sms_sender.py
git commit -m "feat(sms): add SMSSender protocol with console and Twilio impls"
```

---

### Task 3: Refactor `core/otp.py` for namespacing and add phone normalization

**Files:**
- Modify: `backend/app/src/app/core/otp.py`
- Test: `backend/app/tests/test_otp_phone.py` (new)

The change is back-compat: every helper grows a keyword-only `namespace: str = "email"` parameter and the Redis key prefix becomes `otp:{namespace}:…`. Existing callers do not pass `namespace`, so their key shape stays `otp:email:code:{email}`. The previous shape was `otp:code:{email}` — this is a one-time key-shape change (acceptable: no live email OTPs in flight in pre-production, and a stranded key just costs one Redis row that expires in 600s).

- [ ] **Step 1: Write failing tests for phone normalization and namespaced OTP**

```python
# backend/app/tests/test_otp_phone.py
import pytest
import redis.asyncio as aioredis

from app.core.config import settings
from app.core.otp import (
    InvalidPhoneNumber,
    consume_otp_key,
    hash_code,
    normalize_phone,
    request_otp,
    verify_otp,
)


def test_normalize_phone_accepts_indian_e164():
    assert normalize_phone("+919876543210") == "+919876543210"
    assert normalize_phone(" +91 98765 43210 ") == "+919876543210"
    assert normalize_phone("+91-9876543210") == "+919876543210"


def test_normalize_phone_rejects_other_formats():
    for bad in ("9876543210", "+1234567890", "+91 1234567890", "+91987654321", "+9198765432101", ""):
        with pytest.raises(InvalidPhoneNumber):
            normalize_phone(bad)


@pytest.fixture
async def redis_client():
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    yield client
    # clean up phone keys
    async for key in client.scan_iter("otp:phone:*"):
        await client.delete(key)
    await client.aclose()


@pytest.mark.anyio
async def test_namespaced_request_uses_phone_prefix(redis_client):
    phone = "+919876543210"
    code = await request_otp(phone, redis_client, namespace="phone")
    stored = await redis_client.hget(f"otp:phone:code:{phone}", "code_hash")
    assert stored == hash_code(code)


@pytest.mark.anyio
async def test_namespaced_verify_and_consume(redis_client):
    phone = "+919876543210"
    code = await request_otp(phone, redis_client, namespace="phone")
    assert await verify_otp(phone, code, redis_client, namespace="phone") is True
    await consume_otp_key(phone, redis_client, namespace="phone")
    assert await redis_client.exists(f"otp:phone:code:{phone}") == 0


@pytest.mark.anyio
async def test_email_default_namespace_unchanged(redis_client):
    """request_otp() called with no namespace argument must still write to the
    email namespace key shape `otp:email:code:{email}`."""
    email = "user@example.com"
    code = await request_otp(email, redis_client)
    stored = await redis_client.hget(f"otp:email:code:{email}", "code_hash")
    assert stored == hash_code(code)
    await consume_otp_key(email, redis_client)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend/app && uv run pytest tests/test_otp_phone.py -v`
Expected: FAIL — imports of `InvalidPhoneNumber`, `normalize_phone` and `namespace=` kwarg unsupported.

- [ ] **Step 3: Refactor `core/otp.py`**

Replace the contents of `backend/app/src/app/core/otp.py` with:

```python
import hashlib
import hmac
import re
import secrets

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.rate_limit import incr_with_ttl, seconds_until


_PHONE_RE = re.compile(r"^\+91[6-9]\d{9}$")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_phone(raw: str) -> str:
    """Accept Indian E.164 mobile numbers, strip whitespace and hyphens.
    Returns a canonical `+91XXXXXXXXXX` string.

    Raises InvalidPhoneNumber on anything else.
    """
    if not raw:
        raise InvalidPhoneNumber()
    cleaned = re.sub(r"[\s-]", "", raw)
    if not _PHONE_RE.match(cleaned):
        raise InvalidPhoneNumber()
    return cleaned


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str) -> str:
    return hashlib.sha256(f"{settings.OTP_PEPPER}{code}".encode()).hexdigest()


def _key_code(identifier: str, namespace: str = "email") -> str:
    return f"otp:{namespace}:code:{identifier}"


def _key_cooldown(identifier: str, namespace: str = "email") -> str:
    return f"otp:{namespace}:cooldown:{identifier}"


def _key_hourly(identifier: str, namespace: str = "email") -> str:
    return f"otp:{namespace}:hourly:{identifier}"


class RateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after


class InvalidCode(Exception):
    pass


class CodeExpired(Exception):
    pass


class TooManyAttempts(Exception):
    pass


class InvalidPhoneNumber(Exception):
    pass


async def request_otp(
    identifier: str, redis: aioredis.Redis, *, namespace: str = "email"
) -> str:
    """Store a new OTP in Redis. Returns the plaintext code for the caller to send."""
    cooldown = await seconds_until(redis, _key_cooldown(identifier, namespace))
    if cooldown > 0:
        raise RateLimited(retry_after=cooldown)

    hourly = await incr_with_ttl(redis, _key_hourly(identifier, namespace), 3600)
    if hourly > settings.OTP_MAX_PER_HOUR:
        raise RateLimited(
            retry_after=await seconds_until(redis, _key_hourly(identifier, namespace))
        )

    code = generate_code()
    pipe = redis.pipeline()
    pipe.hset(
        _key_code(identifier, namespace),
        mapping={"code_hash": hash_code(code), "attempts": "0"},
    )
    pipe.expire(_key_code(identifier, namespace), settings.OTP_TTL_SECONDS)
    pipe.set(
        _key_cooldown(identifier, namespace), "1", ex=settings.OTP_RESEND_COOLDOWN
    )
    await pipe.execute()
    return code


async def verify_otp(
    identifier: str, code: str, redis: aioredis.Redis, *, namespace: str = "email"
) -> bool:
    """Verify OTP code. Returns True on match; does NOT delete the key."""
    data: dict[str, str] = await redis.hgetall(_key_code(identifier, namespace))  # type: ignore[misc]
    if not data:
        raise CodeExpired()

    if hmac.compare_digest(data.get("code_hash", ""), hash_code(code)):
        return True

    attempts = await redis.hincrby(_key_code(identifier, namespace), "attempts", 1)  # type: ignore[misc]
    if int(attempts) >= settings.OTP_MAX_ATTEMPTS:
        await redis.delete(_key_code(identifier, namespace))
        raise TooManyAttempts()
    raise InvalidCode()


async def consume_otp_key(
    identifier: str, redis: aioredis.Redis, *, namespace: str = "email"
) -> None:
    """Delete OTP code key and rate-limit counters after successful auth."""
    await redis.delete(
        _key_code(identifier, namespace),
        _key_cooldown(identifier, namespace),
        _key_hourly(identifier, namespace),
    )
```

Note: existing email callers in `api/auth.py` already pass an email *and* call `normalize_email` themselves before passing it in — that pattern is preserved. The refactor only changes key shape.

- [ ] **Step 4: Run new tests**

Run: `cd backend/app && uv run pytest tests/test_otp_phone.py -v`
Expected: all pass.

- [ ] **Step 5: Run the full suite to check no regression**

Run: `cd backend/app && uv run pytest -x -q`
Expected: all tests pass (existing email-OTP-related tests will use the new `otp:email:…` key shape; they don't assert on the raw key).

- [ ] **Step 6: Lint + types**

Run: `cd backend/app && uv run ruff check app/core/otp.py && uv run mypy app/core/otp.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/src/app/core/otp.py backend/app/tests/test_otp_phone.py
git commit -m "refactor(otp): namespace OTP helpers and add phone normalization"
```

---

### Task 4: Add `seller_signup` token helpers and rename `seller_otp` claim

**Files:**
- Modify: `backend/app/src/app/core/security.py`
- Modify: `backend/app/src/app/api/auth.py` (only the import lines and the two existing call sites that mint/decode the email-stage token)
- Test: `backend/app/tests/test_security_signup_token.py` (new)

The token type string changes from `seller_otp` → `seller_email`, and a new `seller_signup` type is added. Function names move from `create_email_verification_token` / `decode_email_verification_token` to `create_seller_email_token` / `decode_seller_email_token` for symmetry with the new pair `create_seller_signup_token` / `decode_seller_signup_token`.

- [ ] **Step 1: Write failing tests**

```python
# backend/app/tests/test_security_signup_token.py
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend/app && uv run pytest tests/test_security_signup_token.py -v`
Expected: FAIL — names not imported.

- [ ] **Step 3: Replace the verification-token helpers in `core/security.py`**

In `backend/app/src/app/core/security.py`, replace the existing `create_email_verification_token` and `decode_email_verification_token` functions (lines ~104-134) with:

```python
def create_seller_email_token(email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "type": "seller_email",
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_seller_email_token(token: str) -> str:
    """Validate the seller email-stage token. Returns email on success."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"error": "email_token_expired"},
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_email_token"},
        ) from None
    if payload.get("type") != "seller_email":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_email_token"},
        )
    return str(payload["sub"])


def create_seller_signup_token(email: str, phone: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "phone": phone,
        "type": "seller_signup",
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_seller_signup_token(token: str) -> tuple[str, str]:
    """Validate the seller signup token. Returns (email, phone)."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"error": "signup_token_expired"},
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_signup_token"},
        ) from None
    if payload.get("type") != "seller_signup":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_signup_token"},
        )
    return str(payload["sub"]), str(payload["phone"])
```

- [ ] **Step 4: Update the existing call site in `api/auth.py`**

In `backend/app/src/app/api/auth.py`:

1. Change the import line `from app.core.security import (create_access_token, create_email_verification_token, decode_email_verification_token, get_current_user)` so it imports `create_seller_email_token` and `decode_seller_email_token` instead.
2. In `seller_otp_verify` (around line 171), change `email_token = create_email_verification_token(email)` → `email_token = create_seller_email_token(email)`.
3. In `seller_register` (around line 185), change `email = decode_email_verification_token(body.email_token)` → `email = decode_seller_email_token(body.email_token)`. (This call site will be replaced again in Task 8 when register switches to signup_token; this intermediate change keeps the suite green.)

- [ ] **Step 5: Run new tests**

Run: `cd backend/app && uv run pytest tests/test_security_signup_token.py -v`
Expected: 5 passed.

- [ ] **Step 6: Run full suite**

Run: `cd backend/app && uv run pytest -x -q`
Expected: all pass — existing seller register tests still work because they go through the renamed helper.

- [ ] **Step 7: Lint + types**

Run: `cd backend/app && uv run ruff check app/core/security.py app/api/auth.py && uv run mypy app/core/security.py app/api/auth.py`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add backend/app/src/app/core/security.py backend/app/src/app/api/auth.py backend/app/tests/test_security_signup_token.py
git commit -m "feat(security): add seller signup token; rename email-stage token type"
```

---

### Task 5: Update Pydantic schemas

**Files:**
- Modify: `backend/app/src/app/schemas/sellers.py`

The schema changes are not test-driven directly — they're consumed by the route changes in Tasks 6-8 whose tests will fail without them. We make the change here and rely on the existing `test_seller_register.py` to surface any oversight.

- [ ] **Step 1: Read the current `SellerRegisterBody`**

Run: `cat backend/app/src/app/schemas/sellers.py`

You should see fields including `email_token: str` and `phone: str`. Note the rest of the field list — you must preserve every other field unchanged.

- [ ] **Step 2: Modify the schema**

In `backend/app/src/app/schemas/sellers.py`:

1. In `SellerRegisterBody`, replace `email_token: str` with `signup_token: str`.
2. Remove the `phone: str` field from `SellerRegisterBody` (phone is now sourced from token claims).
3. Add two new schemas at the end of the file:

```python
class SellerPhoneOtpRequestBody(BaseModel):
    email_token: str
    phone: str


class SellerPhoneOtpVerifyBody(BaseModel):
    email_token: str
    phone: str
    code: str
```

(Use `from pydantic import BaseModel` if not already imported.)

- [ ] **Step 3: Run lint + types**

Run: `cd backend/app && uv run ruff check app/schemas/sellers.py && uv run mypy app/schemas/sellers.py`
Expected: no errors.

- [ ] **Step 4: Run the existing test suite**

Run: `cd backend/app && uv run pytest -x -q`
Expected: `test_seller_register.py` tests now FAIL — they construct `SellerRegisterBody` with `email_token` and `phone`. This is intentional; Tasks 8 and 9 fix them.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/schemas/sellers.py
git commit -m "feat(schemas): replace email_token with signup_token; add phone OTP bodies"
```

---

### Task 6: Add `/seller/phone/otp/request` endpoint

**Files:**
- Modify: `backend/app/src/app/api/auth.py`
- Test: `backend/app/tests/test_seller_phone_otp.py` (new — first half)

- [ ] **Step 1: Write failing tests for the request endpoint**

```python
# backend/app/tests/test_seller_phone_otp.py
import pytest
import redis.asyncio as aioredis
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.config import settings
from app.core.security import create_seller_email_token
from app.core.sms import SMSSender, get_sms_sender
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
def _override_sms(recorder: _RecorderSender):
    app.dependency_overrides[get_sms_sender] = lambda: recorder
    yield
    app.dependency_overrides.pop(get_sms_sender, None)


@pytest.fixture(autouse=True)
async def _clean_phone_keys():
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    async for key in client.scan_iter("otp:phone:*"):
        await client.delete(key)
    yield
    async for key in client.scan_iter("otp:phone:*"):
        await client.delete(key)
    await client.aclose()


@pytest.mark.anyio
async def test_phone_request_happy_path(client: AsyncClient, recorder: _RecorderSender):
    email_token = create_seller_email_token("seller@test.com")
    resp = await client.post(
        "/api/v1/auth/seller/phone/otp/request",
        json={"email_token": email_token, "phone": "+919876543210"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["expires_in"] == settings.OTP_TTL_SECONDS
    assert len(recorder.sent) == 1
    to, text = recorder.sent[0]
    assert to == "+919876543210"
    assert "verification code" in text.lower()


@pytest.mark.anyio
async def test_phone_request_rejects_invalid_format(client: AsyncClient):
    email_token = create_seller_email_token("seller@test.com")
    resp = await client.post(
        "/api/v1/auth/seller/phone/otp/request",
        json={"email_token": email_token, "phone": "9876543210"},  # missing +91
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_phone"


@pytest.mark.anyio
async def test_phone_request_rejects_bad_email_token(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/seller/phone/otp/request",
        json={"email_token": "not-a-jwt", "phone": "+919876543210"},
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_phone_request_rejects_duplicate_phone(
    client: AsyncClient, session: AsyncSession
):
    """If a SellerProfile already uses this phone, reject with 409."""
    user = User(email="existing@test.com", role=UserRole.Seller)
    session.add(user)
    await session.flush()
    address = Address(
        line1="A", city="X", state="Maharashtra", postal_code="400001", country="IN"
    )
    session.add(address)
    await session.flush()
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


@pytest.mark.anyio
async def test_phone_request_cooldown(client: AsyncClient):
    email_token = create_seller_email_token("seller@test.com")
    body = {"email_token": email_token, "phone": "+919876543210"}
    first = await client.post("/api/v1/auth/seller/phone/otp/request", json=body)
    assert first.status_code == 200
    second = await client.post("/api/v1/auth/seller/phone/otp/request", json=body)
    assert second.status_code == 429
    assert second.json()["detail"]["error"] == "rate_limited"
    assert "retry_after" in second.json()["detail"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend/app && uv run pytest tests/test_seller_phone_otp.py -v`
Expected: FAIL — endpoint not registered (404).

- [ ] **Step 3: Implement the endpoint**

In `backend/app/src/app/api/auth.py`:

1. Add imports at the top:

```python
from app.core.otp import (
    InvalidPhoneNumber,
    normalize_phone,
)
from app.core.sms import SMSSender, get_sms_sender
from app.core.security import (
    decode_seller_email_token,
)
from app.models.profile import SellerProfile  # already imported, verify
from app.schemas.sellers import (
    SellerPhoneOtpRequestBody,
    SellerPhoneOtpVerifyBody,
)
```

2. Add the new route handler at the bottom of the file (before the file ends):

```python
@router.post("/seller/phone/otp/request")
async def seller_phone_otp_request(
    body: SellerPhoneOtpRequestBody,
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
    sender: SMSSender = Depends(get_sms_sender),
) -> dict:  # type: ignore[type-arg]
    decode_seller_email_token(body.email_token)  # raises if invalid

    try:
        phone = normalize_phone(body.phone)
    except InvalidPhoneNumber:
        raise HTTPException(
            status_code=400, detail={"error": "invalid_phone"}
        ) from None

    existing = await session.exec(
        select(SellerProfile).where(SellerProfile.phone == phone)
    )
    if existing.first():
        raise HTTPException(
            status_code=409, detail={"error": "phone_already_registered"}
        )

    try:
        code = await request_otp(phone, redis, namespace="phone")
    except RateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "retry_after": exc.retry_after},
        ) from exc

    await sender.send(
        to=phone,
        text=(
            f"Your Khana Bazaar seller verification code is: {code}\n"
            "Expires in 10 minutes."
        ),
    )
    return {"ok": True, "expires_in": settings.OTP_TTL_SECONDS}
```

- [ ] **Step 4: Run new tests**

Run: `cd backend/app && uv run pytest tests/test_seller_phone_otp.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run full suite**

Run: `cd backend/app && uv run pytest -x -q --ignore=backend/app/tests/test_seller_register.py`
Expected: all pass except the (knowingly-broken) `test_seller_register.py` which Task 9 fixes.

- [ ] **Step 6: Lint + types**

Run: `cd backend/app && uv run ruff check app/api/auth.py && uv run mypy app/api/auth.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/src/app/api/auth.py backend/app/tests/test_seller_phone_otp.py
git commit -m "feat(auth): add seller phone OTP request endpoint"
```

---

### Task 7: Add `/seller/phone/otp/verify` endpoint

**Files:**
- Modify: `backend/app/src/app/api/auth.py`
- Modify: `backend/app/tests/test_seller_phone_otp.py` (extend)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_seller_phone_otp.py`:

```python
import jwt as pyjwt
from app.core.config import settings as cfg


@pytest.mark.anyio
async def test_phone_verify_returns_signup_token(
    client: AsyncClient, recorder: _RecorderSender
):
    email_token = create_seller_email_token("seller@test.com")
    phone = "+919876543210"
    await client.post(
        "/api/v1/auth/seller/phone/otp/request",
        json={"email_token": email_token, "phone": phone},
    )
    code = recorder.sent[-1][1].split("verification code is: ")[1].split("\n")[0]
    resp = await client.post(
        "/api/v1/auth/seller/phone/otp/verify",
        json={"email_token": email_token, "phone": phone, "code": code},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "signup_token" in body
    decoded = pyjwt.decode(
        body["signup_token"], cfg.JWT_SECRET, algorithms=["HS256"]
    )
    assert decoded["type"] == "seller_signup"
    assert decoded["sub"] == "seller@test.com"
    assert decoded["phone"] == phone


@pytest.mark.anyio
async def test_phone_verify_wrong_code(
    client: AsyncClient, recorder: _RecorderSender
):
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


@pytest.mark.anyio
async def test_phone_verify_too_many_attempts(
    client: AsyncClient, recorder: _RecorderSender
):
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


@pytest.mark.anyio
async def test_phone_verify_no_code_issued(client: AsyncClient):
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
```

(Delete the placeholder `test_phone_verify_happy_path` body if unused.)

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend/app && uv run pytest tests/test_seller_phone_otp.py -v`
Expected: new tests FAIL — endpoint not registered.

- [ ] **Step 3: Implement the endpoint**

In `backend/app/src/app/api/auth.py`, add another route handler after the request one:

```python
@router.post("/seller/phone/otp/verify")
async def seller_phone_otp_verify(
    body: SellerPhoneOtpVerifyBody,
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:  # type: ignore[type-arg]
    email = decode_seller_email_token(body.email_token)

    try:
        phone = normalize_phone(body.phone)
    except InvalidPhoneNumber:
        raise HTTPException(
            status_code=400, detail={"error": "invalid_phone"}
        ) from None

    try:
        await verify_otp(phone, body.code, redis, namespace="phone")
    except CodeExpired:
        raise HTTPException(
            status_code=410, detail={"error": "code_expired_or_used"}
        ) from None
    except TooManyAttempts:
        raise HTTPException(
            status_code=429, detail={"error": "too_many_attempts"}
        ) from None
    except InvalidCode:
        raise HTTPException(
            status_code=400, detail={"error": "invalid_code"}
        ) from None

    await consume_otp_key(phone, redis, namespace="phone")
    signup_token = create_seller_signup_token(email, phone)
    return {"signup_token": signup_token}
```

You will also need to import `create_seller_signup_token` at the top — add to the existing `from app.core.security import (...)` block.

- [ ] **Step 4: Run new tests**

Run: `cd backend/app && uv run pytest tests/test_seller_phone_otp.py -v`
Expected: all pass.

- [ ] **Step 5: Lint + types**

Run: `cd backend/app && uv run ruff check app/api/auth.py && uv run mypy app/api/auth.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/src/app/api/auth.py backend/app/tests/test_seller_phone_otp.py
git commit -m "feat(auth): add seller phone OTP verify endpoint"
```

---

### Task 8: Update `/seller/register` to consume `signup_token`

**Files:**
- Modify: `backend/app/src/app/api/auth.py`

- [ ] **Step 1: Update the imports**

In `backend/app/src/app/api/auth.py`, ensure `decode_seller_signup_token` is imported from `app.core.security`. Remove `decode_seller_email_token` from the `seller_register` handler (it stays imported only if still used by `/seller/phone/otp/*` — yes, it is).

- [ ] **Step 2: Replace the body of `seller_register`**

Find the current `seller_register` handler (around line 175-230). Replace its body so it now decodes the signup token and reads `phone` from claims:

```python
@router.post("/seller/register")
async def seller_register(
    body: SellerRegisterBody,
    session: AsyncSession = Depends(get_db_session),
) -> dict:  # type: ignore[type-arg]
    from app.services.seller_services import (
        replace_profile_services,
        validate_service_ids,
    )

    email, phone = decode_seller_signup_token(body.signup_token)

    # Defence in depth: re-check both email and phone uniqueness at commit time.
    user_exists = await session.exec(select(User).where(User.email == email))
    if user_exists.first():
        raise HTTPException(
            status_code=409, detail={"error": "email_already_registered"}
        )
    phone_exists = await session.exec(
        select(SellerProfile).where(SellerProfile.phone == phone)
    )
    if phone_exists.first():
        raise HTTPException(
            status_code=409, detail={"error": "phone_already_registered"}
        )

    try:
        valid_ids = await validate_service_ids(session, body.service_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    first_name, last_name = split_full_name(body.full_name)
    user = User(email=email, role=UserRole.Seller)
    session.add(user)
    await session.flush()

    address = Address(**address_from_payload(body.address))
    session.add(address)
    await session.flush()

    profile = SellerProfile(
        user_id=user.id,
        first_name=first_name,
        last_name=last_name,
        business_name=body.business_name,
        phone=phone,
        gst_number=body.gst_number or None,
        fssai_license=body.fssai_license or None,
        bank_account_number=body.bank_account_number or None,
        bank_ifsc=body.bank_ifsc or None,
        business_address_id=address.id,
    )
    session.add(profile)
    await session.flush()
    await replace_profile_services(session, profile, valid_ids)

    await session.commit()
    await session.refresh(user)

    token = create_access_token(user)
    full_name = compose_full_name(first_name, last_name)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _user_payload(user, full_name),
    }
```

- [ ] **Step 3: Run lint + types**

Run: `cd backend/app && uv run ruff check app/api/auth.py && uv run mypy app/api/auth.py`
Expected: no errors.

- [ ] **Step 4: Run the suite (existing register tests still failing — fixed in Task 9)**

Run: `cd backend/app && uv run pytest tests/test_seller_register.py -v`
Expected: failures — tests still pass `email_token` and `phone` in the body. This is fine; Task 9 fixes them.

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/api/auth.py
git commit -m "feat(auth): seller register consumes signup_token; phone from claims"
```

---

### Task 9: Update `tests/test_seller_register.py` for the new contract

**Files:**
- Modify: `backend/app/tests/test_seller_register.py`

- [ ] **Step 1: Locate the helper that builds the register payload**

Open `backend/app/tests/test_seller_register.py`. Find `_register_payload(email_token, ...)` and the per-test calls to `create_email_verification_token`. The helper builds a dict body with `email_token` and `phone`.

- [ ] **Step 2: Replace the helper + token-mint helper**

Replace the helper so it now:

1. Takes a `signup_token` argument instead of `email_token`.
2. Drops `phone` from the returned dict.

```python
from app.core.security import create_seller_signup_token


def _register_payload(signup_token: str, *, service_id: int, **overrides):
    base = {
        "signup_token": signup_token,
        "full_name": "Test Seller",
        "business_name": "Test Co",
        "service_ids": [service_id],
        "address": _make_address_payload(),
        "gst_number": None,
        "fssai_license": None,
        "bank_account_number": None,
        "bank_ifsc": None,
    }
    base.update(overrides)
    return base
```

(Adjust to match the existing helper's exact signature and the existing `_make_address_payload` name.)

- [ ] **Step 3: Update every test in the file**

For each test that previously did:

```python
token = create_email_verification_token("seller@test.com")
payload = _register_payload(token, ...)
```

Replace with:

```python
token = create_seller_signup_token("seller@test.com", "+919876543210")
payload = _register_payload(token, ...)
```

For `test_seller_register_invalid_token`, send `"signup_token": "not-a-jwt"` and expect `400 invalid_signup_token`.
For `test_seller_register_wrong_token_type`, mint a `seller_email`-typed token (using `create_seller_email_token`) and expect `400 invalid_signup_token`.

- [ ] **Step 4: Add a new test for duplicate phone at register time**

```python
@pytest.mark.anyio
async def test_seller_register_duplicate_phone(
    client: AsyncClient, session, seeded_grocery_service_id: int
):
    """If two parallel registrations race, the second commit must reject."""
    user = User(email="first@test.com", role=UserRole.Seller)
    session.add(user)
    await session.flush()
    address = Address(line1="A", city="X", state="Maharashtra", postal_code="400001", country="IN")
    session.add(address)
    await session.flush()
    session.add(
        SellerProfile(
            user_id=user.id,
            first_name="A",
            last_name="B",
            business_name="First",
            phone="+919876543210",
            business_address_id=address.id,
        )
    )
    await session.commit()

    token = create_seller_signup_token("second@test.com", "+919876543210")
    resp = await client.post(
        "/api/v1/auth/seller/register",
        json=_register_payload(token, service_id=seeded_grocery_service_id),
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "phone_already_registered"
```

- [ ] **Step 5: Run the full suite**

Run: `cd backend/app && uv run pytest -x -q`
Expected: ALL tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/tests/test_seller_register.py
git commit -m "test(seller): switch register tests to signup_token; add duplicate phone case"
```

---

### Task 10: Frontend wizard — state model, step indicator, and back-navigation

**Files:**
- Modify: `frontend/src/app/(operator)/seller/signup/page.tsx`

This task only changes structure (state, indicator, navigation). UI for the new steps is in Tasks 11-12. Keep the page compiling at every step.

- [ ] **Step 1: Update state declarations**

In `SellerSignupPageInner` (around line 65), update the state block:

```tsx
const [currentStep, setCurrentStep] = useState(1);
const [email, setEmail] = useState("");
const [code, setCode] = useState("");                    // email OTP
const [emailToken, setEmailToken] = useState("");
const [phone, setPhone] = useState("");                  // 10-digit local part
const [phoneCode, setPhoneCode] = useState("");          // NEW: phone OTP
const [signupToken, setSignupToken] = useState("");      // NEW
const [fullName, setFullName] = useState("");
const [businessName, setBusinessName] = useState("");
const [serviceIds, setServiceIds] = useState<number[]>([]);
const [services, setServices] = useState<Service[]>([]);
const [address, setAddress] = useState<Address>(emptyAddress());
const [gstNumber, setGstNumber] = useState("");
const [fssaiLicense, setFssaiLicense] = useState("");
const [bankAccountNumber, setBankAccountNumber] = useState("");
const [bankIfsc, setBankIfsc] = useState("");
```

- [ ] **Step 2: Update the `StepIndicator` to render 8 steps**

Replace its `[1, 2, 3, 4, 5, 6]` with `[1, 2, 3, 4, 5, 6, 7, 8]` and the `i < 5` connector check with `i < 7`. Update `Step {current} of 6` to `Step {current} of 8`.

- [ ] **Step 3: Update the resubmit jump target**

In the `useEffect` that handles `isResubmit` (around line 110), the existing code does `setCurrentStep(3)`. Change it to `setCurrentStep(5)` so resubmit users land on the renamed personal-info step (which now collects `full_name` only). Keep the profile pre-fills as-is — `setPhone(profile.phone)` is still useful for displaying their existing phone in the review step.

- [ ] **Step 4: Verify the page still compiles**

Run: `cd frontend && npm run build`
Expected: build succeeds with no type errors. (If a step's JSX references the not-yet-added phone-OTP step, comment it out for now — Tasks 11-12 add it.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/signup/page.tsx
git commit -m "refactor(seller-signup): add phone-OTP state slots and 8-step indicator"
```

---

### Task 11: Frontend wizard — Phone (Step 3) UI

**Files:**
- Modify: `frontend/src/app/(operator)/seller/signup/page.tsx`
- Modify: `frontend/src/app/(operator)/seller/signup/seller-signup.module.css` (if a phone-prefix adornment style is needed; reuse existing input styles otherwise)

- [ ] **Step 1: Add the step 3 panel**

After the existing email-OTP step (currently `currentStep === 2`), insert:

```tsx
{currentStep === 3 && (
  <div className={styles.stepPanel}>
    <h2>Verify your phone number</h2>
    <p>We&apos;ll text you a 6-digit code to confirm this number.</p>
    <label htmlFor="phone">Mobile number</label>
    <div className={styles.phoneFieldRow}>
      <span className={styles.phonePrefix}>+91</span>
      <input
        id="phone"
        type="tel"
        inputMode="numeric"
        maxLength={10}
        value={phone}
        onChange={(e) => {
          const digits = e.target.value.replace(/\D/g, "").slice(0, 10);
          setPhone(digits);
          clearError("phone");
        }}
        placeholder="9876543210"
      />
    </div>
    {fieldErrors.phone && <p className={styles.fieldError}>{fieldErrors.phone}</p>}
    <div className={styles.stepActions}>
      <button type="button" onClick={() => setCurrentStep(2)}>Back</button>
      <button
        type="button"
        onClick={handleSendPhoneCode}
        disabled={submitting || !PHONE_REGEX.test(phone)}
      >
        Send code
      </button>
    </div>
  </div>
)}
```

- [ ] **Step 2: Add the `handleSendPhoneCode` handler**

In the same component, add (near the existing `handleSendOtp` / `handleResendOtp`):

```tsx
const handleSendPhoneCode = async () => {
  setSubmitting(true);
  try {
    await post("/api/v1/auth/seller/phone/otp/request", {
      email_token: emailToken,
      phone: `+91${phone}`,
    });
    setCurrentStep(4);
  } catch (err) {
    if (err instanceof ApiError) {
      const detail = err.detail as { error?: string } | string;
      const code = typeof detail === "object" ? detail.error : undefined;
      if (code === "phone_already_registered") {
        setFieldErrors((p) => ({
          ...p,
          phone: "This phone number is already registered.",
        }));
      } else if (code === "invalid_phone") {
        setFieldErrors((p) => ({
          ...p,
          phone: "Enter a valid 10-digit Indian mobile number.",
        }));
      } else if (code === "rate_limited") {
        setToast({ message: "Please wait before requesting another code.", type: "error" });
      } else {
        setToast({ message: err.message, type: "error" });
      }
    }
  } finally {
    setSubmitting(false);
  }
};
```

Make sure `ApiError` is imported from `@/lib/api` at the top of the file.

- [ ] **Step 3: Add CSS for the +91 prefix adornment**

In `seller-signup.module.css`, add (or reuse if a similar input row exists):

```css
.phoneFieldRow {
  display: flex;
  align-items: stretch;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.phonePrefix {
  display: inline-flex;
  align-items: center;
  padding: 0 0.75rem;
  background: var(--color-surface-2);
  color: var(--color-fg-muted);
  font-weight: 500;
}
.phoneFieldRow input {
  border: none;
  flex: 1;
  padding: 0.5rem 0.75rem;
}
```

(Inspect the file first — if equivalent styles exist for other prefix inputs, reuse instead.)

- [ ] **Step 4: Manual smoke test**

Run: `cd frontend && npm run dev` and `cd backend/app && uv run uvicorn app.main:app --reload` (in separate terminals). Open `http://localhost:3000/seller/signup`, complete steps 1-2 with a test email, advance to step 3, enter a number, click "Send code". The backend log should show `[SMS] to=+91…` with the code. Step should auto-advance to step 4 (which is not yet implemented — page may render blank, that's fine for this task).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/signup/page.tsx frontend/src/app/\(operator\)/seller/signup/seller-signup.module.css
git commit -m "feat(seller-signup): add phone-entry step (step 3)"
```

---

### Task 12: Frontend wizard — Phone-OTP (Step 4) UI

**Files:**
- Modify: `frontend/src/app/(operator)/seller/signup/page.tsx`

- [ ] **Step 1: Add the step 4 panel**

```tsx
{currentStep === 4 && (
  <div className={styles.stepPanel}>
    <h2>Enter the code we sent</h2>
    <p>Sent to +91{phone}</p>
    <label htmlFor="phone-code">6-digit code</label>
    <input
      id="phone-code"
      type="text"
      inputMode="numeric"
      maxLength={6}
      value={phoneCode}
      onChange={(e) => {
        const digits = e.target.value.replace(/\D/g, "").slice(0, 6);
        setPhoneCode(digits);
        clearError("phoneCode");
      }}
    />
    {fieldErrors.phoneCode && (
      <p className={styles.fieldError}>{fieldErrors.phoneCode}</p>
    )}
    <div className={styles.stepActions}>
      <button
        type="button"
        onClick={() => {
          setPhoneCode("");
          setCurrentStep(3);
        }}
      >
        Back
      </button>
      <button
        type="button"
        onClick={handleVerifyPhoneCode}
        disabled={submitting || phoneCode.length !== 6}
      >
        Verify
      </button>
    </div>
    <button
      type="button"
      onClick={handleSendPhoneCode}
      disabled={submitting}
      className={styles.linkButton}
    >
      Resend code
    </button>
  </div>
)}
```

- [ ] **Step 2: Add the `handleVerifyPhoneCode` handler**

```tsx
const handleVerifyPhoneCode = async () => {
  setSubmitting(true);
  try {
    const res = await post<{ signup_token: string }>(
      "/api/v1/auth/seller/phone/otp/verify",
      {
        email_token: emailToken,
        phone: `+91${phone}`,
        code: phoneCode,
      }
    );
    setSignupToken(res.signup_token);
    setPhoneCode("");
    setCurrentStep(5);
  } catch (err) {
    if (err instanceof ApiError) {
      const detail = err.detail as { error?: string } | string;
      const code = typeof detail === "object" ? detail.error : undefined;
      if (code === "invalid_code") {
        setFieldErrors((p) => ({ ...p, phoneCode: "Incorrect code. Try again." }));
      } else if (code === "code_expired_or_used") {
        setFieldErrors((p) => ({ ...p, phoneCode: "Code expired. Resend a new one." }));
      } else if (code === "too_many_attempts") {
        setToast({
          message: "Too many wrong attempts. Resend a new code.",
          type: "error",
        });
      } else {
        setToast({ message: err.message, type: "error" });
      }
    }
  } finally {
    setSubmitting(false);
  }
};
```

- [ ] **Step 3: Manual smoke test**

Run frontend + backend dev servers as in Task 11. Walk steps 1→2→3→4. Enter the code from the backend `[SMS]` log. Verify advances to step 5 (which still shows the existing personal-info JSX — Task 13 will trim it).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/signup/page.tsx
git commit -m "feat(seller-signup): add phone-OTP verify step (step 4)"
```

---

### Task 13: Frontend wizard — adjust steps 5-8 numbering and personal-info content

**Files:**
- Modify: `frontend/src/app/(operator)/seller/signup/page.tsx`

The pre-existing steps (personal info, business info, compliance, review) all have hardcoded `currentStep === N` checks and `setCurrentStep(N+1)` / `setCurrentStep(N-1)` button handlers. Each of these N values must shift by +2.

- [ ] **Step 1: Re-key every existing step**

Find every occurrence of:

```
currentStep === 3   →   currentStep === 5
currentStep === 4   →   currentStep === 6
currentStep === 5   →   currentStep === 7
currentStep === 6   →   currentStep === 8

setCurrentStep(2)   →   stays 2 (Back from old step 3 was email OTP)
                        BUT old step 3's "Back" was setCurrentStep(2) — now in step 5,
                        the "Back" button must go to step 4 (phone OTP). Change accordingly.
setCurrentStep(3) → setCurrentStep(5)
setCurrentStep(4) → setCurrentStep(6)
setCurrentStep(5) → setCurrentStep(7)
setCurrentStep(6) → setCurrentStep(8)
```

Walk the file in order. The Back-button targets must match the new ordering: step 5 → back to 4; step 6 → back to 5; etc.

- [ ] **Step 2: Remove the phone input from the personal-info step**

In what is now step 5 (was step 3), remove the `<label htmlFor="phone">…</label>` block and its `<input>`. Also remove the `if (!PHONE_REGEX.test(phone)) { errors.phone = ...; }` check from the local validator for step 5 — phone is now token-bound and not entered here.

The personal-info step now has only `full_name`.

- [ ] **Step 3: Manual compile + smoke test**

Run: `cd frontend && npm run build`
Expected: build succeeds.

Then `npm run dev` and walk all 8 steps end-to-end (do not submit yet — Task 14 wires the final POST). Confirm Back/Next move correctly between every adjacent step.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/signup/page.tsx
git commit -m "refactor(seller-signup): renumber steps 5-8; drop phone input from personal info"
```

---

### Task 14: Frontend wizard — final submit using `signup_token`

**Files:**
- Modify: `frontend/src/app/(operator)/seller/signup/page.tsx`

- [ ] **Step 1: Update the submit handler**

Find `handleSubmit` (or equivalent name) — the function that POSTs `/api/v1/auth/seller/register`. Update the body it sends:

```tsx
const handleSubmit = async () => {
  setSubmitting(true);
  try {
    const res = await post<{ access_token: string; user: User }>(
      "/api/v1/auth/seller/register",
      {
        signup_token: signupToken,
        full_name: fullName,
        business_name: businessName,
        service_ids: serviceIds,
        address,
        gst_number: gstNumber || null,
        fssai_license: fssaiLicense || null,
        bank_account_number: bankAccountNumber || null,
        bank_ifsc: bankIfsc || null,
      }
    );
    localStorage.setItem("kb_token", res.access_token);
    router.push("/seller/signup/pending");
  } catch (err) {
    if (err instanceof ApiError) {
      const detail = err.detail as { error?: string } | string;
      const code = typeof detail === "object" ? detail.error : undefined;
      if (code === "signup_token_expired" || code === "invalid_signup_token") {
        setToast({
          message: "Phone verification expired. Please verify your phone number again.",
          type: "error",
        });
        setSignupToken("");
        setPhoneCode("");
        setCurrentStep(3);
      } else if (code === "phone_already_registered") {
        setToast({
          message: "This phone number was just registered. Please use a different number.",
          type: "error",
        });
        setSignupToken("");
        setCurrentStep(3);
      } else if (code === "email_already_registered") {
        setToast({
          message: "This email is already registered. Sign in instead.",
          type: "error",
        });
      } else {
        setToast({ message: err.message, type: "error" });
      }
    }
  } finally {
    setSubmitting(false);
  }
};
```

(Adjust to match the existing handler's exact name and surrounding patterns. Preserve any analytics or post-success side effects.)

- [ ] **Step 2: Manual end-to-end test**

Run frontend + backend dev servers. Walk all 8 steps with a fresh email + a phone number not in the DB. On submit, verify:

- Browser redirects to `/seller/signup/pending`.
- Backend DB has new `User` (role=Seller), new `SellerProfile.phone` = `+91<entered>`.
- A second submit attempt with the same email or phone returns the toast and bumps the user back to the right step.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/signup/page.tsx
git commit -m "feat(seller-signup): submit register with signup_token"
```

---

### Task 15: Update documentation

**Files:**
- Modify: `docs/seller_signup.md`
- Modify: `docs/flows.md`
- Modify: `docs/azure_deployment.md`
- Modify: `CLAUDE.md` (env vars section, optional gotchas)

- [ ] **Step 1: Update `docs/seller_signup.md`**

Update the wizard step list to reflect 8 steps. Add a "Phone OTP" sub-section under "OTP-bridge" describing:

- Endpoint pair `/auth/seller/phone/otp/{request,verify}`.
- The `signup_token` claim shape.
- Sandbox behaviour: `SMS_PROVIDER=console` logs the code to stdout.

- [ ] **Step 2: Update `docs/flows.md`**

In the seller-signup flow diagram/section, insert phone-OTP between email-OTP and personal-info entry. Update any sequence diagram if present.

- [ ] **Step 3: Update `docs/azure_deployment.md`**

Add Twilio credentials to the env-var table:

| Var | Example | Source |
|-----|---------|--------|
| `SMS_PROVIDER` | `twilio` | App config |
| `TWILIO_ACCOUNT_SID` | `AC...` | Key Vault |
| `TWILIO_AUTH_TOKEN` | (secret) | Key Vault |
| `TWILIO_FROM_NUMBER` | `+15005550006` | App config |

- [ ] **Step 4: Update `CLAUDE.md` env-var section**

Under "Backend `.env`" optional vars, add:

```
- EMAIL_PROVIDER (`console` default | `resend`)
- SMS_PROVIDER (`console` default | `twilio`)
- TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER (only when SMS_PROVIDER=twilio)
```

- [ ] **Step 5: Commit**

```bash
git add docs/ CLAUDE.md
git commit -m "docs: document seller phone-OTP flow and Twilio env vars"
```

---

### Task 16: Open the PR

- [ ] **Step 1: Push the branch**

```bash
git push -u origin feat/seller-phone-otp
```

- [ ] **Step 2: Create the PR**

```bash
gh pr create --title "feat(seller): phone-OTP verification on signup" --body "$(cat <<'EOF'
## Summary
- Adds an SMS-OTP gate to seller signup between email-OTP and the data-entry steps.
- Sandbox dispatch via `SMS_PROVIDER=console`; production via `twilio` (raw httpx, no SDK).
- Replaces the single-purpose `email_token` hand-off into `/auth/seller/register` with a combined `signup_token` whose JWT claims bind verified email + verified phone.
- Reuses the existing Redis OTP primitives by namespacing the keys (`otp:phone:*` alongside `otp:email:*`).

## Test plan
- [ ] `uv run pytest -v` — full backend suite (incl. new `test_seller_phone_otp.py`)
- [ ] Manual end-to-end signup: fresh email + new phone → wizard completes → seller exists in DB
- [ ] Duplicate phone surfaced before SMS dispatch (409)
- [ ] `signup_token` expired flow loops user back to phone step
EOF
)"
```

(Wait for explicit user approval before pushing or opening the PR — see CLAUDE.md.)

---

## Self-review

### Spec coverage

- Wizard re-ordering (8 steps): Tasks 10-13 cover.
- `core/sms.py` with Console + Twilio: Task 2.
- Config additions: Task 1.
- `core/otp.py` namespacing + `normalize_phone`: Task 3.
- `core/security.py` token rename + new signup token: Task 4.
- Schema changes: Task 5.
- New `/seller/phone/otp/request` and `/verify`: Tasks 6-7.
- `/seller/register` consumes `signup_token`: Task 8.
- Backend tests (new + updated): Tasks 6, 7, 9.
- Frontend wrappers: covered by inline `post()` calls (no `lib/api.ts` change needed — it's a thin wrapper, every existing wizard call uses `post()` directly).
- Resubmit flow: out of scope per spec; jump target updated to step 5 in Task 10.
- Docs: Task 15.
- PR: Task 16.

### Type / signature consistency

- `create_seller_signup_token(email, phone)` ↔ `decode_seller_signup_token(token) -> tuple[str, str]` — matched in Tasks 4, 7, 8.
- `request_otp(identifier, redis, *, namespace="email")` — same signature used by Tasks 6, 7 callers.
- `normalize_phone(raw) -> str` raises `InvalidPhoneNumber` — caught explicitly in Tasks 6, 7.
- Frontend state vars: `signupToken` consistent across Tasks 10, 12, 14.
- Error codes: `invalid_phone`, `phone_already_registered`, `rate_limited`, `invalid_code`, `too_many_attempts`, `code_expired_or_used`, `signup_token_expired`, `invalid_signup_token`, `email_already_registered` — matched between backend (Tasks 6-9) and frontend (Tasks 11, 12, 14).

### Placeholder scan

- No "TBD" / "fill in" lines.
- Every step that changes code shows the code.
- Every test step shows test code.
- Resubmit out-of-scope is called out; not deferred.
