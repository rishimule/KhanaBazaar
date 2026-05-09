<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Email-OTP Auth Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Firebase-based auth with self-hosted email-OTP + stateless JWT so the project has zero Firebase dependencies.

**Architecture:** Backend generates a 6-digit OTP, stores a sha256+pepper hash in Redis with a 10-min TTL, sends the code via Resend (or prints it in dev), then issues an HS256 JWT on successful verification. Frontend drops the Firebase SDK; AuthContext bootstraps from `localStorage` via `GET /auth/me`. The unified passwordless flow handles both new and returning users — new users are prompted for their name only when the backend returns `needs_name: true`.

**Tech Stack:** PyJWT (HS256), httpx (Resend API), fakeredis.aioredis (test doubles), redis.asyncio (OTP/rate-limit), Next.js 16 AuthContext (Bearer header), two-step email→code login page.

---

## File Map

**Backend — create:**
- `backend/app/src/app/core/redis.py` — `get_redis` FastAPI dependency (singleton `redis.asyncio.Redis` pool)
- `backend/app/src/app/core/email.py` — `EmailSender` Protocol, `ConsoleEmailSender`, `ResendEmailSender`, `get_email_sender` factory
- `backend/app/src/app/core/otp.py` — `request_otp`, `verify_otp`, `consume_otp_key`, Redis key logic, rate-limit errors
- `backend/app/src/app/core/rate_limit.py` — `incr_with_ttl`, `seconds_until` (thin Redis helpers)
- `backend/app/tests/test_jwt.py` — JWT round-trip, tamper, expiry
- `backend/app/tests/test_otp.py` — OTP unit tests with fakeredis

**Backend — rewrite:**
- `backend/app/src/app/core/security.py` — drop Firebase, add JWT create/decode, keep dependency signatures
- `backend/app/src/app/api/auth.py` — two OTP endpoints + `/me`
- `backend/app/tests/test_auth.py` — full HTTP integration suite

**Backend — modify:**
- `backend/app/src/app/core/config.py` — drop Firebase settings, add JWT/OTP/email settings
- `backend/app/src/app/models/base.py` — drop `firebase_uid`, make `email` required+unique
- `backend/app/src/app/worker.py` — add `send_otp_email_async` Celery task
- `backend/app/pyproject.toml` — remove `firebase-admin`, add `pyjwt[crypto]`, move `httpx` to main, add `fakeredis` dev dep
- `backend/app/.env.example` — replace Firebase vars with JWT/OTP/email vars
- `backend/app/tests/test_stores.py` — remove `firebase_uid` from mock users
- `backend/app/tests/test_db.py` — remove `firebase_uid` from User constructor
- `backend/app/scripts/seed_database.py` — remove Firebase, seed users by email

**Backend — new migration:**
- `backend/app/migrations/versions/<autogen>.py` — drop `firebase_uid`, make `email` NOT NULL + unique

**Frontend — rewrite:**
- `frontend/src/lib/AuthContext.tsx` — drop Firebase SDK, `requestOtp`/`verifyOtp`/`logout`, localStorage bootstrap
- `frontend/src/app/login/page.tsx` — three-step email→code→name form

**Frontend — modify:**
- `frontend/src/types/index.ts` — drop `firebase_uid`, make `email: string`
- `frontend/package.json` — remove `firebase` dep

**Frontend — delete:**
- `frontend/src/lib/firebase.ts`

---

## Task 1: Dependencies & Config

**Files:**
- Modify: `backend/app/pyproject.toml`
- Modify: `backend/app/src/app/core/config.py`
- Modify: `backend/app/.env.example`
- Add values to: `backend/app/.env` (local dev — not committed)

- [ ] **Step 1: Update pyproject.toml**

Replace the `[project] dependencies` and `[dependency-groups]` sections so `firebase-admin` is gone, `pyjwt[crypto]` is added to main deps, `httpx` moves from dev to main, and `fakeredis` is added to dev:

```toml
# backend/app/pyproject.toml
[project]
name = "app"
version = "0.1.0"
description = "Add your description here"
readme = "README.md"
authors = [
    { name = "Khana Bazaar Developer", email = "developer@khanabazaar.local" }
]
requires-python = ">=3.12"
dependencies = [
    "alembic>=1.18.4",
    "asyncpg>=0.31.0",
    "celery>=5.6.2",
    "fastapi>=0.135.1",
    "httpx>=0.28.1",
    "pydantic-settings>=2.13.1",
    "pyjwt[crypto]>=2.10.0",
    "redis>=7.3.0",
    "sqlmodel>=0.0.37",
    "uvicorn>=0.41.0",
]

[project.scripts]
app = "app:main"

[build-system]
requires = ["uv_build>=0.10.9,<0.11.0"]
build-backend = "uv_build"

[dependency-groups]
dev = [
    "aiosqlite>=0.22.1",
    "fakeredis>=2.25.0",
    "mypy>=1.19.1",
    "pytest>=9.0.2",
    "pytest-asyncio>=1.3.0",
    "pytest-cov>=7.0.0",
    "ruff>=0.15.5",
]

[tool.ruff]
line-length = 88
target-version = "py312"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "C", "B"]
ignore = ["E501", "B008", "W191"]

[tool.mypy]
python_version = "3.12"
strict = true
ignore_missing_imports = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
```

- [ ] **Step 2: Sync dependencies**

```bash
cd backend/app
uv sync
```
Expected: lock file updated, `firebase-admin` gone, `pyjwt` and `fakeredis` present.

- [ ] **Step 3: Replace config.py**

```python
# backend/app/src/app/core/config.py
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Khana Bazaar API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # JWT
    JWT_SECRET: str
    JWT_EXPIRES_HOURS: int = 24

    # OTP
    OTP_PEPPER: str
    OTP_TTL_SECONDS: int = 600
    OTP_MAX_ATTEMPTS: int = 5
    OTP_RESEND_COOLDOWN: int = 60
    OTP_MAX_PER_HOUR: int = 5

    # Email: "console" (dev/test) or "resend" (production)
    EMAIL_PROVIDER: str = "console"
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = ""

    DATABASE_URL: str
    REDIS_URL: str

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)


settings = Settings()
```

- [ ] **Step 4: Update .env.example**

```ini
# backend/app/.env.example
# Khana Bazaar Backend Environment Variables Template
# Copy this file to .env and replace the values with your actual configuration.

PROJECT_NAME="Khana Bazaar API"
ENVIRONMENT="development"

# PostgreSQL Database
DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/khanabazaar"

# Redis Broker/Cache
REDIS_URL="redis://localhost:6379/0"

# JWT — generate with: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET="change-me-use-secrets-token-hex-32"
JWT_EXPIRES_HOURS=24

# OTP — generate with: python -c "import secrets; print(secrets.token_hex(16))"
OTP_PEPPER="change-me-use-secrets-token-hex-16"
OTP_TTL_SECONDS=600
OTP_MAX_ATTEMPTS=5
OTP_RESEND_COOLDOWN=60
OTP_MAX_PER_HOUR=5

# Email: "console" (prints codes to stdout) or "resend" (production)
EMAIL_PROVIDER="console"
RESEND_API_KEY=""
RESEND_FROM_EMAIL=""
```

- [ ] **Step 5: Add required vars to local .env**

Edit `backend/app/.env` (NOT committed) — add these lines. Generate values with the commands in the comments above:

```ini
JWT_SECRET="dev-jwt-secret-at-least-32-chars-ok"
OTP_PEPPER="dev-otp-pepper-16chars"
EMAIL_PROVIDER="console"
```

- [ ] **Step 6: Verify config loads**

```bash
cd backend/app
uv run python -c "from app.core.config import settings; print(settings.JWT_SECRET[:8])"
```
Expected: prints first 8 chars of JWT_SECRET (no import errors).

- [ ] **Step 7: Commit**

```bash
git add backend/app/pyproject.toml backend/app/uv.lock backend/app/src/app/core/config.py backend/app/.env.example
git commit -m "chore: replace firebase-admin with pyjwt+httpx+fakeredis, update config"
```

---

## Task 2: DB Model & Alembic Migration

**Files:**
- Modify: `backend/app/src/app/models/base.py`
- Create: `backend/app/migrations/versions/<autogen>.py` (filename set by Alembic)

- [ ] **Step 1: Update models/base.py**

Replace `UserBase` — drop `firebase_uid`, make `email` required and unique:

```python
# backend/app/src/app/models/base.py
import enum
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import DateTime, Field, SQLModel


class UserRole(str, enum.Enum):
    Customer = "customer"
    Seller = "seller"
    Admin = "admin"


class BaseSchema(SQLModel):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )


class UserBase(SQLModel):
    email: str = Field(index=True, unique=True, nullable=False)
    is_active: bool = Field(default=True)
    role: UserRole = Field(default=UserRole.Customer)
    full_name: Optional[str] = Field(default=None)


class User(BaseSchema, UserBase, table=True):
    pass


class ItemBase(SQLModel):
    title: str = Field(index=True, nullable=False)
    description: Optional[str] = Field(default=None)
    owner_id: int = Field(foreign_key="user.id", nullable=False)


class Item(BaseSchema, ItemBase, table=True):
    pass
```

- [ ] **Step 2: Generate the migration**

```bash
cd backend/app
uv run alembic revision --autogenerate -m "drop_firebase_uid_make_email_required"
```
Expected: new file in `migrations/versions/` with a hash prefix.

- [ ] **Step 3: Inspect and fix the generated migration**

Open the new migration file. Alembic may not auto-detect all changes correctly (especially dropping a unique index). Ensure the `upgrade()` and `downgrade()` look exactly like this (replace the function bodies, preserve the boilerplate):

```python
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.drop_index("ix_user_firebase_uid", table_name="user")
    op.drop_column("user", "firebase_uid")
    op.alter_column("user", "email", nullable=False)
    op.create_unique_constraint("uq_user_email", "user", ["email"])


def downgrade() -> None:
    op.drop_constraint("uq_user_email", "user", type_="unique")
    op.alter_column("user", "email", nullable=True)
    op.add_column(
        "user",
        sa.Column("firebase_uid", sa.VARCHAR(), autoincrement=False, nullable=True),
    )
    op.create_index("ix_user_firebase_uid", "user", ["firebase_uid"], unique=True)
```

- [ ] **Step 4: Apply migration to dev DB**

```bash
cd backend/app
uv run alembic upgrade head
```
Expected: `Running upgrade ... -> <hash>, drop_firebase_uid_make_email_required`

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/models/base.py backend/app/migrations/versions/
git commit -m "feat: drop firebase_uid, make email required+unique on user table"
```

---

## Task 3: Redis Dependency

**Files:**
- Create: `backend/app/src/app/core/redis.py`

- [ ] **Step 1: Create core/redis.py**

```python
# backend/app/src/app/core/redis.py
from functools import lru_cache

import redis.asyncio as aioredis

from .config import settings


@lru_cache
def _redis_pool() -> aioredis.Redis:
    return aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def get_redis() -> aioredis.Redis:
    return _redis_pool()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/src/app/core/redis.py
git commit -m "feat: add get_redis FastAPI dependency (singleton async Redis pool)"
```

---

## Task 4: JWT Security Module + test_jwt.py

**Files:**
- Rewrite: `backend/app/src/app/core/security.py`
- Create: `backend/app/tests/test_jwt.py`

- [ ] **Step 1: Write failing tests first**

```python
# backend/app/tests/test_jwt.py
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token
from app.models.base import User, UserRole


@pytest.fixture
def sample_user() -> User:
    return User(id=42, email="jwt@example.com", role=UserRole.Customer, is_active=True)


def test_create_token_encodes_sub_and_role(sample_user: User) -> None:
    token = create_access_token(sample_user)
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    assert payload["sub"] == "42"
    assert payload["role"] == "customer"


def test_decode_valid_token_returns_payload(sample_user: User) -> None:
    token = create_access_token(sample_user)
    payload = decode_access_token(token)
    assert payload["sub"] == "42"


def test_decode_tampered_token_raises_401(sample_user: User) -> None:
    token = create_access_token(sample_user)
    tampered = token[:-4] + "wxyz"
    with pytest.raises(HTTPException) as exc:
        decode_access_token(tampered)
    assert exc.value.status_code == 401


def test_decode_expired_token_raises_401() -> None:
    payload = {
        "sub": "1",
        "role": "customer",
        "iat": datetime.now(timezone.utc) - timedelta(hours=25),
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        decode_access_token(token)
    assert exc.value.status_code == 401


def test_decode_wrong_secret_raises_401(sample_user: User) -> None:
    token = jwt.encode(
        {
            "sub": "42",
            "role": "customer",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "wrong-secret",
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc:
        decode_access_token(token)
    assert exc.value.status_code == 401
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
cd backend/app
uv run pytest tests/test_jwt.py -v
```
Expected: `ImportError: cannot import name 'decode_access_token' from 'app.core.security'`

- [ ] **Step 3: Rewrite core/security.py**

```python
# backend/app/src/app/core/security.py
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.db.session import get_db_session
from app.models.base import User, UserRole

security = HTTPBearer()


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "role": user.role.value,
        "iat": now,
        "exp": now + timedelta(hours=settings.JWT_EXPIRES_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


async def verify_access_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    return decode_access_token(credentials.credentials)


async def get_current_user(
    payload: dict[str, Any] = Depends(verify_access_token),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    user_id = payload.get("sub")
    user = await session.get(User, int(user_id))  # type: ignore[arg-type]
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


async def get_current_seller(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in (UserRole.Seller, UserRole.Admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough privileges. Seller role required.",
        )
    return current_user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.Admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough privileges. Admin role required.",
        )
    return current_user
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
cd backend/app
uv run pytest tests/test_jwt.py -v
```
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/core/security.py backend/app/tests/test_jwt.py
git commit -m "feat: replace Firebase token verification with PyJWT (HS256)"
```

---

## Task 5: Rate-Limit Helpers

**Files:**
- Create: `backend/app/src/app/core/rate_limit.py`

- [ ] **Step 1: Create core/rate_limit.py**

```python
# backend/app/src/app/core/rate_limit.py
import redis.asyncio as aioredis


async def incr_with_ttl(redis: aioredis.Redis, key: str, ttl: int) -> int:
    """Increment counter; set TTL only on first increment (atomic-enough for MVP)."""
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, ttl)
    return count


async def seconds_until(redis: aioredis.Redis, key: str) -> int:
    """Seconds remaining on key TTL. Returns 0 if key does not exist."""
    ttl = await redis.ttl(key)
    return max(0, ttl)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/src/app/core/rate_limit.py
git commit -m "feat: add Redis-backed rate-limit helpers (incr_with_ttl, seconds_until)"
```

---

## Task 6: Email Module

**Files:**
- Create: `backend/app/src/app/core/email.py`

- [ ] **Step 1: Create core/email.py**

```python
# backend/app/src/app/core/email.py
import logging
from typing import Protocol

import httpx

from .config import settings

logger = logging.getLogger(__name__)


class EmailSender(Protocol):
    async def send(self, to: str, subject: str, text: str) -> None: ...


class ConsoleEmailSender:
    async def send(self, to: str, subject: str, text: str) -> None:
        logger.info("EMAIL to=%s subject=%r body=%r", to, subject, text)


class ResendEmailSender:
    async def send(self, to: str, subject: str, text: str) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json={
                    "from": settings.RESEND_FROM_EMAIL,
                    "to": [to],
                    "subject": subject,
                    "text": text,
                },
                timeout=10,
            )
            resp.raise_for_status()


def get_email_sender() -> EmailSender:
    if settings.EMAIL_PROVIDER == "resend":
        return ResendEmailSender()
    return ConsoleEmailSender()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/src/app/core/email.py
git commit -m "feat: add EmailSender protocol with ConsoleEmailSender and ResendEmailSender"
```

---

## Task 7: OTP Module + test_otp.py

**Files:**
- Create: `backend/app/src/app/core/otp.py`
- Create: `backend/app/tests/test_otp.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/app/tests/test_otp.py
import re

import fakeredis.aioredis
import pytest

from app.core.otp import (
    CodeExpired,
    InvalidCode,
    RateLimited,
    TooManyAttempts,
    consume_otp_key,
    generate_code,
    hash_code,
    request_otp,
    verify_otp,
)


@pytest.fixture
def fake_redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def test_generate_code_is_6_digits() -> None:
    for _ in range(20):
        code = generate_code()
        assert re.fullmatch(r"\d{6}", code), f"Got {code!r}"


def test_hash_code_is_sha256_hex_not_plaintext() -> None:
    code = "123456"
    hashed = hash_code(code)
    assert hashed != code
    assert re.fullmatch(r"[0-9a-f]{64}", hashed)


async def test_request_otp_stores_hashed_code(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    code = await request_otp("test@example.com", fake_redis)
    data = await fake_redis.hgetall("otp:code:test@example.com")
    assert data["code_hash"] == hash_code(code)
    assert data["code_hash"] != code
    assert int(data["attempts"]) == 0


async def test_request_otp_normalizes_email(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    await request_otp("  UPPER@Example.COM  ", fake_redis)
    assert await fake_redis.exists("otp:code:upper@example.com") == 1


async def test_verify_correct_code_returns_true(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    code = await request_otp("user@example.com", fake_redis)
    assert await verify_otp("user@example.com", code, fake_redis) is True


async def test_verify_wrong_code_raises_invalid_code(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    await request_otp("user@example.com", fake_redis)
    with pytest.raises(InvalidCode):
        await verify_otp("user@example.com", "000000", fake_redis)


async def test_verify_wrong_code_increments_attempts(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    await request_otp("user@example.com", fake_redis)
    with pytest.raises(InvalidCode):
        await verify_otp("user@example.com", "000000", fake_redis)
    data = await fake_redis.hgetall("otp:code:user@example.com")
    assert int(data["attempts"]) == 1


async def test_five_failures_raises_too_many_attempts(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    await request_otp("user@example.com", fake_redis)
    for _ in range(4):
        with pytest.raises(InvalidCode):
            await verify_otp("user@example.com", "000000", fake_redis)
    with pytest.raises(TooManyAttempts):
        await verify_otp("user@example.com", "000000", fake_redis)
    assert await fake_redis.exists("otp:code:user@example.com") == 0


async def test_missing_key_raises_code_expired(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    with pytest.raises(CodeExpired):
        await verify_otp("ghost@example.com", "123456", fake_redis)


async def test_resend_cooldown_blocks_second_request(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    await request_otp("user@example.com", fake_redis)
    with pytest.raises(RateLimited) as exc_info:
        await request_otp("user@example.com", fake_redis)
    assert exc_info.value.retry_after > 0


async def test_consume_deletes_all_keys(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    await request_otp("user@example.com", fake_redis)
    await consume_otp_key("user@example.com", fake_redis)
    assert await fake_redis.exists("otp:code:user@example.com") == 0
    assert await fake_redis.exists("otp:cooldown:user@example.com") == 0
    assert await fake_redis.exists("otp:hourly:user@example.com") == 0
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
cd backend/app
uv run pytest tests/test_otp.py -v
```
Expected: `ImportError: cannot import name 'request_otp' from 'app.core.otp'`

- [ ] **Step 3: Create core/otp.py**

```python
# backend/app/src/app/core/otp.py
import hashlib
import hmac
import secrets

import redis.asyncio as aioredis

from .config import settings
from .rate_limit import incr_with_ttl, seconds_until


def normalize_email(email: str) -> str:
    return email.strip().lower()


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str) -> str:
    return hashlib.sha256(f"{settings.OTP_PEPPER}{code}".encode()).hexdigest()


def _key_code(email: str) -> str:
    return f"otp:code:{email}"


def _key_cooldown(email: str) -> str:
    return f"otp:cooldown:{email}"


def _key_hourly(email: str) -> str:
    return f"otp:hourly:{email}"


class RateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after


class InvalidCode(Exception):
    pass


class CodeExpired(Exception):
    pass


class TooManyAttempts(Exception):
    pass


async def request_otp(email: str, redis: aioredis.Redis) -> str:
    """Store a new OTP. Returns the plaintext code for the caller to send."""
    email = normalize_email(email)

    cooldown = await seconds_until(redis, _key_cooldown(email))
    if cooldown > 0:
        raise RateLimited(retry_after=cooldown)

    hourly = await incr_with_ttl(redis, _key_hourly(email), 3600)
    if hourly > settings.OTP_MAX_PER_HOUR:
        raise RateLimited(retry_after=await seconds_until(redis, _key_hourly(email)))

    code = generate_code()
    pipe = redis.pipeline()
    pipe.hset(_key_code(email), mapping={"code_hash": hash_code(code), "attempts": "0"})
    pipe.expire(_key_code(email), settings.OTP_TTL_SECONDS)
    pipe.set(_key_cooldown(email), "1", ex=settings.OTP_RESEND_COOLDOWN)
    await pipe.execute()

    return code


async def verify_otp(email: str, code: str, redis: aioredis.Redis) -> bool:
    """Verify OTP. Returns True on match; does NOT delete the key.

    Raises CodeExpired, InvalidCode, or TooManyAttempts on failure.
    Caller must call consume_otp_key() after successful auth.
    """
    email = normalize_email(email)
    data: dict[str, str] = await redis.hgetall(_key_code(email))
    if not data:
        raise CodeExpired()

    if hmac.compare_digest(data.get("code_hash", ""), hash_code(code)):
        return True

    attempts = await redis.hincrby(_key_code(email), "attempts", 1)
    if attempts >= settings.OTP_MAX_ATTEMPTS:
        await redis.delete(_key_code(email))
        raise TooManyAttempts()
    raise InvalidCode()


async def consume_otp_key(email: str, redis: aioredis.Redis) -> None:
    """Delete OTP key and rate-limit counters after successful auth."""
    email = normalize_email(email)
    await redis.delete(_key_code(email), _key_cooldown(email), _key_hourly(email))
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
cd backend/app
uv run pytest tests/test_otp.py -v
```
Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/src/app/core/otp.py backend/app/tests/test_otp.py
git commit -m "feat: add OTP module (generate, hash, request, verify, consume) with tests"
```

---

## Task 8: Auth Endpoints + test_auth.py

**Files:**
- Rewrite: `backend/app/src/app/api/auth.py`
- Rewrite: `backend/app/tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/app/tests/test_auth.py
import re
from typing import AsyncGenerator

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient

from app import app
from app.core.email import EmailSender, get_email_sender
from app.core.redis import get_redis


class FakeEmailSender:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, to: str, subject: str, text: str) -> None:
        self.sent.append({"to": to, "subject": subject, "text": text})


def _extract_code(text: str) -> str:
    match = re.search(r"\b(\d{6})\b", text)
    assert match, f"No 6-digit code found in: {text!r}"
    return match.group(1)


@pytest.fixture
def fake_redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def fake_sender() -> FakeEmailSender:
    return FakeEmailSender()


@pytest.fixture
async def auth_client(
    fake_redis: fakeredis.aioredis.FakeRedis,
    fake_sender: FakeEmailSender,
) -> AsyncGenerator[dict, None]:
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_email_sender] = lambda: fake_sender
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield {"client": client, "redis": fake_redis, "sender": fake_sender}
    app.dependency_overrides.pop(get_redis, None)
    app.dependency_overrides.pop(get_email_sender, None)


async def test_otp_request_returns_ok(auth_client: dict) -> None:
    resp = await auth_client["client"].post(
        "/api/v1/auth/otp/request", json={"email": "user@example.com"}
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert len(auth_client["sender"].sent) == 1


async def test_otp_request_same_response_for_unknown_email(auth_client: dict) -> None:
    resp = await auth_client["client"].post(
        "/api/v1/auth/otp/request", json={"email": "brand-new@example.com"}
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


async def test_returning_user_gets_token(auth_client: dict, session) -> None:
    from app.models.base import User, UserRole
    user = User(email="returning@example.com", full_name="Ret", role=UserRole.Customer)
    session.add(user)
    await session.commit()

    c = auth_client["client"]
    sender = auth_client["sender"]
    await c.post("/api/v1/auth/otp/request", json={"email": "returning@example.com"})
    code = _extract_code(sender.sent[-1]["text"])
    resp = await c.post(
        "/api/v1/auth/otp/verify",
        json={"email": "returning@example.com", "code": code},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_name"] is False
    assert data["access_token"] is not None
    assert data["user"]["email"] == "returning@example.com"


async def test_new_user_needs_name_then_gets_token(auth_client: dict) -> None:
    c = auth_client["client"]
    sender = auth_client["sender"]

    await c.post("/api/v1/auth/otp/request", json={"email": "new@example.com"})
    code = _extract_code(sender.sent[-1]["text"])

    resp1 = await c.post(
        "/api/v1/auth/otp/verify", json={"email": "new@example.com", "code": code}
    )
    assert resp1.status_code == 200
    assert resp1.json()["needs_name"] is True
    assert resp1.json()["access_token"] is None

    resp2 = await c.post(
        "/api/v1/auth/otp/verify",
        json={"email": "new@example.com", "code": code, "full_name": "New User"},
    )
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["needs_name"] is False
    assert data["access_token"] is not None
    assert data["user"]["full_name"] == "New User"
    assert data["user"]["role"] == "customer"


async def test_wrong_code_returns_400(auth_client: dict) -> None:
    await auth_client["client"].post(
        "/api/v1/auth/otp/request", json={"email": "user@example.com"}
    )
    resp = await auth_client["client"].post(
        "/api/v1/auth/otp/verify",
        json={"email": "user@example.com", "code": "000000"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_code"


async def test_five_wrong_codes_returns_429(auth_client: dict) -> None:
    c = auth_client["client"]
    await c.post("/api/v1/auth/otp/request", json={"email": "user@example.com"})
    for _ in range(4):
        await c.post(
            "/api/v1/auth/otp/verify",
            json={"email": "user@example.com", "code": "000000"},
        )
    resp = await c.post(
        "/api/v1/auth/otp/verify",
        json={"email": "user@example.com", "code": "000000"},
    )
    assert resp.status_code == 429
    assert resp.json()["detail"]["error"] == "too_many_attempts"


async def test_missing_key_returns_410(auth_client: dict) -> None:
    resp = await auth_client["client"].post(
        "/api/v1/auth/otp/verify",
        json={"email": "ghost@example.com", "code": "123456"},
    )
    assert resp.status_code == 410
    assert resp.json()["detail"]["error"] == "code_expired_or_used"


async def test_rapid_resend_returns_429(auth_client: dict) -> None:
    c = auth_client["client"]
    await c.post("/api/v1/auth/otp/request", json={"email": "user@example.com"})
    resp = await c.post("/api/v1/auth/otp/request", json={"email": "user@example.com"})
    assert resp.status_code == 429
    assert resp.json()["detail"]["error"] == "rate_limited"


async def test_me_endpoint_returns_authenticated_user(auth_client: dict) -> None:
    c = auth_client["client"]
    sender = auth_client["sender"]
    await c.post("/api/v1/auth/otp/request", json={"email": "me@example.com"})
    code = _extract_code(sender.sent[-1]["text"])
    verify = await c.post(
        "/api/v1/auth/otp/verify",
        json={"email": "me@example.com", "code": code, "full_name": "Test Me"},
    )
    token = verify.json()["access_token"]
    resp = await c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@example.com"
```

- [ ] **Step 2: Run tests — expect failure (routes not yet rewritten)**

```bash
cd backend/app
uv run pytest tests/test_auth.py -v
```
Expected: failures like `404 Not Found` on `/api/v1/auth/otp/request` (old `/login` route still present).

- [ ] **Step 3: Rewrite api/auth.py**

```python
# backend/app/src/app/api/auth.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.email import EmailSender, get_email_sender
from app.core.otp import (
    CodeExpired,
    InvalidCode,
    RateLimited,
    TooManyAttempts,
    normalize_email,
    consume_otp_key,
    request_otp,
    verify_otp,
)
from app.core.redis import get_redis
from app.core.security import create_access_token, get_current_user
from app.db.session import get_db_session
from app.models.base import User, UserRole

router = APIRouter()


class OTPRequestBody(BaseModel):
    email: EmailStr


class OTPVerifyBody(BaseModel):
    email: EmailStr
    code: str
    full_name: str | None = None


@router.post("/otp/request")
async def otp_request(
    body: OTPRequestBody,
    redis: aioredis.Redis = Depends(get_redis),
    sender: EmailSender = Depends(get_email_sender),
) -> dict:
    try:
        code = await request_otp(str(body.email), redis)
    except RateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "retry_after": exc.retry_after},
        )
    await sender.send(
        to=str(body.email),
        subject="Your Khana Bazaar login code",
        text=f"Your one-time login code is: {code}\n\nThis code expires in 10 minutes.",
    )
    return {"ok": True, "expires_in": settings.OTP_TTL_SECONDS}


@router.post("/otp/verify")
async def otp_verify(
    body: OTPVerifyBody,
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    email = normalize_email(str(body.email))

    try:
        await verify_otp(email, body.code, redis)
    except CodeExpired:
        raise HTTPException(status_code=410, detail={"error": "code_expired_or_used"})
    except TooManyAttempts:
        raise HTTPException(status_code=429, detail={"error": "too_many_attempts"})
    except InvalidCode:
        raise HTTPException(status_code=400, detail={"error": "invalid_code"})

    result = await session.exec(select(User).where(User.email == email))
    user = result.first()

    if user is None:
        if not body.full_name:
            return {"access_token": None, "token_type": None, "user": None, "needs_name": True}
        user = User(email=email, full_name=body.full_name.strip(), role=UserRole.Customer)
        session.add(user)
        await session.commit()
        await session.refresh(user)

    await consume_otp_key(email, redis)
    token = create_access_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user.model_dump(),
        "needs_name": False,
    }


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict:
    return user.model_dump()
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
cd backend/app
uv run pytest tests/test_auth.py -v
```
Expected: `9 passed`

- [ ] **Step 5: Run full test suite**

```bash
cd backend/app
uv run pytest -v
```
Expected: most tests pass. `test_stores.py` may fail because of `firebase_uid` in mock users — that's fixed in Task 10.

- [ ] **Step 6: Commit**

```bash
git add backend/app/src/app/api/auth.py backend/app/tests/test_auth.py
git commit -m "feat: replace /login with /otp/request, /otp/verify, /me endpoints"
```

---

## Task 9: Celery Email Task

**Files:**
- Modify: `backend/app/src/app/worker.py`

- [ ] **Step 1: Add send_otp_email_async task to worker.py**

```python
# backend/app/src/app/worker.py
import asyncio
import time
from typing import Any

from app.core.celery_app import celery_app


@celery_app.task(name="test_celery_task", bind=True)  # type: ignore
def test_celery_task(self: Any, word: str) -> str:
    time.sleep(2)
    return f"Celery processed the word: {word}"


@celery_app.task(name="send_otp_email_async")  # type: ignore
def send_otp_email_async(to: str, code: str) -> None:
    """Send an OTP code email via the configured provider (sync wrapper for Celery)."""
    import httpx
    from app.core.config import settings

    if settings.EMAIL_PROVIDER == "resend":
        import httpx as _httpx
        resp = _httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={
                "from": settings.RESEND_FROM_EMAIL,
                "to": [to],
                "subject": "Your Khana Bazaar login code",
                "text": f"Your one-time login code is: {code}\n\nExpires in 10 minutes.",
            },
            timeout=10,
        )
        resp.raise_for_status()
    else:
        import logging
        logging.getLogger(__name__).info("EMAIL to=%s code=%s", to, code)
```

Note: `api/auth.py` currently calls `sender.send()` directly (inline). The Celery task is available if you want to swap to async dispatch — replace `await sender.send(...)` in `otp_request` with `send_otp_email_async.delay(str(body.email), code)`. Both work; inline is simpler for MVP.

- [ ] **Step 2: Commit**

```bash
git add backend/app/src/app/worker.py
git commit -m "feat: add send_otp_email_async Celery task for background email dispatch"
```

---

## Task 10: Update Existing Tests

**Files:**
- Modify: `backend/app/tests/test_stores.py`
- Modify: `backend/app/tests/test_db.py`

- [ ] **Step 1: Fix test_stores.py — remove firebase_uid from mock users**

Open `backend/app/tests/test_stores.py` and replace lines 10-12:

```python
# Old — REMOVE these lines:
mock_admin = User(id=1, firebase_uid="admin_123", email="admin@kb.com", full_name="Admin", role=UserRole.Admin, is_active=True)
mock_seller = User(id=2, firebase_uid="seller_123", email="seller@kb.com", full_name="Seller", role=UserRole.Seller, is_active=True)
mock_customer = User(id=3, firebase_uid="cust_123", email="cust@kb.com", full_name="Customer", role=UserRole.Customer, is_active=True)

# New — replace with:
mock_admin = User(id=1, email="admin@kb.com", full_name="Admin", role=UserRole.Admin, is_active=True)
mock_seller = User(id=2, email="seller@kb.com", full_name="Seller", role=UserRole.Seller, is_active=True)
mock_customer = User(id=3, email="cust@kb.com", full_name="Customer", role=UserRole.Customer, is_active=True)
```

- [ ] **Step 2: Fix test_db.py — remove firebase_uid**

Replace the entire test in `backend/app/tests/test_db.py`:

```python
# backend/app/tests/test_db.py
import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import User


async def test_create_user(session: AsyncSession) -> None:
    new_user = User(email="test_db_user@example.com", full_name="Test DB User")
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)

    assert new_user.id is not None
    assert new_user.email == "test_db_user@example.com"

    statement = select(User).where(User.email == "test_db_user@example.com")
    result = await session.exec(statement)
    db_user = result.first()

    assert db_user is not None
    assert db_user.id == new_user.id

    await session.delete(db_user)
    await session.commit()
```

- [ ] **Step 3: Run full test suite — expect all pass**

```bash
cd backend/app
uv run pytest -v
```
Expected: all tests pass (test_jwt, test_otp, test_auth, test_stores, test_db, test_tasks).

- [ ] **Step 4: Run linter + type checker**

```bash
cd backend/app
uv run ruff check .
uv run mypy .
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tests/test_stores.py backend/app/tests/test_db.py
git commit -m "test: remove firebase_uid from test fixtures, update test_db for new schema"
```

---

## Task 11: Seed Script

**Files:**
- Modify: `backend/app/scripts/seed_database.py`

- [ ] **Step 1: Rewrite seed_database.py**

Replace the entire file:

```python
#!/usr/bin/env python3
"""
Khana Bazaar — Database Seed Script
====================================
Populates PostgreSQL with categories, products, stores, inventory,
and test user accounts (no Firebase required).

Usage (from backend/app/):
    PYTHONPATH=src uv run python scripts/seed_database.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.base import User, UserRole
from app.models.catalog import Category, MasterProduct
from app.models.store import Store, StoreInventory


TEST_USERS = [
    {"email": "admin@khanabazaar.dev", "display_name": "Platform Admin", "role": UserRole.Admin},
    {"email": "seller@khanabazaar.dev", "display_name": "Ravi Sharma", "role": UserRole.Seller},
    {"email": "seller2@khanabazaar.dev", "display_name": "Krishna Patel", "role": UserRole.Seller},
    {"email": "seller3@khanabazaar.dev", "display_name": "Balaji Ramaswamy", "role": UserRole.Seller},
    {"email": "customer@khanabazaar.dev", "display_name": "Priya Verma", "role": UserRole.Customer},
]

CATEGORIES = [
    {"name": "Fruits & Vegetables", "description": "Fresh produce from local farms"},
    {"name": "Dairy & Bakery", "description": "Milk, paneer, bread, and baked goods"},
    {"name": "Staples & Grains", "description": "Rice, atta, dal, and cooking essentials"},
    {"name": "Snacks & Beverages", "description": "Chips, biscuits, tea, coffee, and cold drinks"},
]

PRODUCTS = [
    {"name": "Fresh Tomatoes", "description": "Firm, red tomatoes", "category_idx": 0, "image_url": "/images/products/tomatoes.jpg", "base_price": 40},
    {"name": "Green Coriander Bunch", "description": "Fresh dhania", "category_idx": 0, "image_url": "/images/products/coriander.jpg", "base_price": 15},
    {"name": "Onions (Pyaaz)", "description": "Medium-sized onions", "category_idx": 0, "image_url": "/images/products/onions.jpg", "base_price": 35},
    {"name": "Amul Taza Milk (1L)", "description": "Toned milk", "category_idx": 1, "image_url": "/images/products/milk.jpg", "base_price": 54},
    {"name": "Amul Paneer (200g)", "description": "Fresh cottage cheese", "category_idx": 1, "image_url": "/images/products/paneer.jpg", "base_price": 90},
    {"name": "Britannia Bread (400g)", "description": "Soft white sandwich bread", "category_idx": 1, "image_url": "/images/products/bread.jpg", "base_price": 45},
    {"name": "Toor Dal (1kg)", "description": "Premium arhar dal", "category_idx": 2, "image_url": "/images/products/toor-dal.jpg", "base_price": 160},
    {"name": "Basmati Rice (5kg)", "description": "Long grain aged basmati", "category_idx": 2, "image_url": "/images/products/rice.jpg", "base_price": 450},
    {"name": "Aashirvaad Atta (5kg)", "description": "Whole wheat flour", "category_idx": 2, "image_url": "/images/products/atta.jpg", "base_price": 280},
    {"name": "Lay's Classic Salted (52g)", "description": "Crispy potato chips", "category_idx": 3, "image_url": "/images/products/lays.jpg", "base_price": 20},
    {"name": "Tata Tea Gold (500g)", "description": "Premium Assam & Darjeeling blend", "category_idx": 3, "image_url": "/images/products/tea.jpg", "base_price": 270},
    {"name": "Parle-G Biscuits (800g)", "description": "India's iconic glucose biscuits", "category_idx": 3, "image_url": "/images/products/parle-g.jpg", "base_price": 80},
]

STORES = [
    {"name": "Sharma General Store", "address": "12, MG Road, Sector 14, Gurugram, Haryana 122001", "seller_idx": 1},
    {"name": "Krishna Supermart", "address": "45, Nehru Nagar, Andheri West, Mumbai, Maharashtra 400058", "seller_idx": 2},
    {"name": "Balaji Fresh Market", "address": "78, Rajaji Street, T. Nagar, Chennai, Tamil Nadu 600017", "seller_idx": 3},
]

INVENTORIES = [
    (0, 0, 42, 50), (0, 1, 18, 30), (0, 2, 38, 60),
    (0, 3, 56, 20), (0, 4, 95, 15),
    (0, 6, 165, 25), (0, 7, 460, 10), (0, 8, 285, 12),
    (0, 9, 20, 100), (0, 10, 275, 18), (0, 11, 82, 40),
    (1, 0, 45, 40), (1, 3, 54, 35), (1, 4, 92, 20),
    (1, 5, 48, 25), (1, 6, 158, 30),
    (1, 9, 20, 60), (1, 10, 268, 15), (1, 11, 78, 50),
    (2, 0, 38, 80), (2, 1, 12, 50), (2, 2, 32, 70),
    (2, 3, 55, 15), (2, 7, 440, 8), (2, 8, 278, 10),
    (2, 10, 272, 12),
]


async def seed() -> None:
    print("\n Khana Bazaar — Seeding Database\n")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    async with AsyncSession(engine) as session:

        print("1  Inserting users ...")
        db_users: list[User] = []
        for u in TEST_USERS:
            existing = await session.exec(select(User).where(User.email == u["email"]))
            user = existing.first()
            if user:
                print(f"  already exists: {u['email']}")
                db_users.append(user)
            else:
                user = User(email=u["email"], full_name=u["display_name"], role=u["role"], is_active=True)
                session.add(user)
                await session.flush()
                print(f"  created: {u['email']} (id={user.id}, role={user.role.value})")
                db_users.append(user)

        print("\n2  Inserting categories ...")
        cat_ids: list[int] = []
        for c in CATEGORIES:
            existing = await session.exec(select(Category).where(Category.name == c["name"]))
            cat = existing.first()
            if cat:
                assert cat.id is not None
                cat_ids.append(cat.id)
            else:
                cat = Category(name=c["name"], description=c["description"])
                session.add(cat)
                await session.flush()
                assert cat.id is not None
                cat_ids.append(cat.id)
                print(f"  created: {c['name']}")

        print("\n3  Inserting products ...")
        product_ids: list[int] = []
        for p in PRODUCTS:
            existing = await session.exec(select(MasterProduct).where(MasterProduct.name == p["name"]))
            prod = existing.first()
            if prod:
                assert prod.id is not None
                product_ids.append(prod.id)
            else:
                prod = MasterProduct(
                    name=p["name"], description=p["description"],
                    category_id=cat_ids[p["category_idx"]],
                    image_url=p["image_url"], base_price=p["base_price"],
                )
                session.add(prod)
                await session.flush()
                assert prod.id is not None
                product_ids.append(prod.id)
                print(f"  created: {p['name']}")

        print("\n4  Inserting stores ...")
        store_ids: list[int] = []
        for s in STORES:
            seller = db_users[s["seller_idx"]]
            assert seller.id is not None
            existing = await session.exec(select(Store).where(Store.name == s["name"]))
            store = existing.first()
            if store:
                assert store.id is not None
                store_ids.append(store.id)
            else:
                store = Store(name=s["name"], address=s["address"], seller_id=seller.id, is_active=True)
                session.add(store)
                await session.flush()
                assert store.id is not None
                store_ids.append(store.id)
                print(f"  created: {s['name']}")

        print("\n5  Inserting inventory ...")
        for store_idx, prod_idx, price, stock in INVENTORIES:
            sid = store_ids[store_idx]
            pid = product_ids[prod_idx]
            existing = await session.exec(
                select(StoreInventory).where(StoreInventory.store_id == sid, StoreInventory.product_id == pid)
            )
            if not existing.first():
                inv = StoreInventory(store_id=sid, product_id=pid, price=price, stock=stock, is_available=stock > 0)
                session.add(inv)

        await session.commit()

    await engine.dispose()
    print("\nSeeding complete!")
    print("\nTest accounts — sign in with email OTP at http://localhost:3000/login:")
    print("  EMAIL_PROVIDER=console: codes appear in backend stdout")
    for u in TEST_USERS:
        print(f"  {u['role'].value:<8}  {u['email']}")


if __name__ == "__main__":
    asyncio.run(seed())
```

- [ ] **Step 2: Run seed script against dev DB**

Ensure docker-compose is running, migration is applied, then:

```bash
cd backend/app
PYTHONPATH=src uv run python scripts/seed_database.py
```
Expected: `Seeding complete!` with user/store counts printed.

- [ ] **Step 3: Commit**

```bash
git add backend/app/scripts/seed_database.py
git commit -m "chore: remove Firebase from seed script, provision users by email"
```

---

## Task 12: Frontend — Types, Package, Env

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/package.json`
- Delete: `frontend/src/lib/firebase.ts`
- Modify: `frontend/.env.example`
- Modify: `frontend/.env.local` (not committed)

- [ ] **Step 1: Update types/index.ts**

Replace the `User` interface (lines 18-24):

```typescript
/** User model matching backend User(BaseSchema, UserBase). */
export interface User extends BaseSchema {
  email: string;
  is_active: boolean;
  role: UserRole;
  full_name?: string;
}
```

- [ ] **Step 2: Remove firebase from package.json**

In `frontend/package.json`, delete the `"firebase": "..."` line from `dependencies`.

- [ ] **Step 3: Delete firebase.ts**

```bash
rm frontend/src/lib/firebase.ts
```

- [ ] **Step 4: Update frontend/.env.example**

Replace contents:

```ini
# Khana Bazaar Frontend Environment Variables Template
# Copy this file to .env.local

# Backend API base URL
NEXT_PUBLIC_API_URL="http://localhost:8000"
```

- [ ] **Step 5: Remove Firebase vars from frontend/.env.local**

Edit `frontend/.env.local` — remove the `NEXT_PUBLIC_FIREBASE_*` lines. Keep only:

```ini
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **Step 6: Reinstall deps**

```bash
cd frontend
npm install
```
Expected: `package-lock.json` updated, `firebase` packages removed from `node_modules`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/index.ts frontend/package.json frontend/package-lock.json frontend/.env.example
git rm frontend/src/lib/firebase.ts
git commit -m "chore: remove Firebase SDK from frontend, update User type"
```

---

## Task 13: Frontend — AuthContext Rewrite

**Files:**
- Rewrite: `frontend/src/lib/AuthContext.tsx`

- [ ] **Step 1: Rewrite AuthContext.tsx**

```typescript
// frontend/src/lib/AuthContext.tsx
"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { User, UserRole } from "@/types";

interface AuthContextValue {
  dbUser: User | null;
  token: string | null;
  loading: boolean;
  requestOtp: (email: string) => Promise<void>;
  verifyOtp: (
    email: string,
    code: string,
    fullName?: string
  ) => Promise<{ user: User; needsName: boolean }>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "kb_token";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [dbUser, setDbUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem(TOKEN_KEY);
    if (!stored) {
      setLoading(false);
      return;
    }
    fetch(`${API_BASE}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${stored}` },
    })
      .then((res) => {
        if (!res.ok) {
          localStorage.removeItem(TOKEN_KEY);
          return null;
        }
        return res.json() as Promise<User>;
      })
      .then((user) => {
        if (user) {
          setToken(stored);
          setDbUser(user);
        }
      })
      .catch(() => localStorage.removeItem(TOKEN_KEY))
      .finally(() => setLoading(false));
  }, []);

  const requestOtp = useCallback(async (email: string): Promise<void> => {
    const res = await fetch(`${API_BASE}/api/v1/auth/otp/request`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      const detail = body?.detail;
      if (detail?.error === "rate_limited") {
        throw new Error(
          `Please wait ${detail.retry_after} seconds before requesting a new code.`
        );
      }
      throw new Error("Failed to send code. Please try again.");
    }
  }, []);

  const verifyOtp = useCallback(
    async (
      email: string,
      code: string,
      fullName?: string
    ): Promise<{ user: User; needsName: boolean }> => {
      const res = await fetch(`${API_BASE}/api/v1/auth/otp/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, code, full_name: fullName ?? null }),
      });
      const data = await res.json();
      if (!res.ok) {
        const error = data?.detail?.error;
        if (error === "invalid_code")
          throw new Error("Incorrect code. Please try again.");
        if (error === "too_many_attempts")
          throw new Error("Too many attempts. Please request a new code.");
        if (error === "code_expired_or_used")
          throw new Error("Code expired. Please request a new one.");
        throw new Error("Verification failed.");
      }
      if (data.needs_name) {
        return { user: null as unknown as User, needsName: true };
      }
      localStorage.setItem(TOKEN_KEY, data.access_token);
      setToken(data.access_token);
      setDbUser(data.user as User);
      return { user: data.user as User, needsName: false };
    },
    []
  );

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setDbUser(null);
  }, []);

  const value = useMemo(
    () => ({ dbUser, token, loading, requestOtp, verifyOtp, logout }),
    [dbUser, token, loading, requestOtp, verifyOtp, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}

/** Hook to get a role-ready auth guard. Returns { authorized, loading, role }. */
export function useRequireRole(requiredRole: UserRole) {
  const { dbUser, loading } = useAuth();
  return {
    authorized: !loading && dbUser !== null && dbUser.role === requiredRole,
    loading,
    user: dbUser,
    role: dbUser?.role ?? null,
  };
}
```

- [ ] **Step 2: Run TypeScript type check**

```bash
cd frontend
npm run build 2>&1 | head -40
```
Expected: errors only about pages that still import `login` (e.g., `login/page.tsx`) — fixed in next task. No errors from AuthContext itself.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/AuthContext.tsx
git commit -m "feat: rewrite AuthContext — drop Firebase, add requestOtp/verifyOtp/logout"
```

---

## Task 14: Frontend — Login Page Rewrite

**Files:**
- Rewrite: `frontend/src/app/login/page.tsx`

- [ ] **Step 1: Rewrite login/page.tsx**

```typescript
// frontend/src/app/login/page.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { User } from "@/types";
import styles from "./page.module.css";

type Step = "email" | "code" | "name";

function getRedirect(user: User): string {
  if (user.role === "admin") return "/admin";
  if (user.role === "seller") return "/seller";
  return "/stores";
}

export default function LoginPage() {
  const router = useRouter();
  const { requestOtp, verifyOtp, dbUser } = useAuth();
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (dbUser) {
    router.push(getRedirect(dbUser));
    return null;
  }

  const handleRequestOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await requestOtp(email);
      setStep("code");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send code.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleVerifyCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await verifyOtp(email, code);
      if (result.needsName) {
        setStep("name");
      } else {
        router.push(getRedirect(result.user));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmitName = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await verifyOtp(email, code, fullName);
      router.push(getRedirect(result.user));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create account.");
    } finally {
      setSubmitting(false);
    }
  };

  const subtitle =
    step === "email"
      ? "Enter your email to sign in or create an account"
      : step === "code"
      ? `Enter the 6-digit code sent to ${email}`
      : "One last step — what should we call you?";

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <div className={styles.cardLogo}>🛍️</div>
          <h1 className={styles.cardTitle}>
            Welcome to{" "}
            <span className={styles.cardTitleAccent}>KhanaBazaar</span>
          </h1>
          <p className={styles.cardSubtitle}>{subtitle}</p>
        </div>

        {step === "email" && (
          <form className={styles.form} onSubmit={handleRequestOtp}>
            {error && <div className={styles.error}>{error}</div>}
            <div className={styles.inputGroup}>
              <label className={styles.label} htmlFor="login-email">
                Email
              </label>
              <input
                id="login-email"
                className={styles.input}
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </div>
            <button
              type="submit"
              className={styles.submitBtn}
              disabled={submitting}
            >
              {submitting ? "Sending code…" : "Send code"}
            </button>
          </form>
        )}

        {step === "code" && (
          <form className={styles.form} onSubmit={handleVerifyCode}>
            {error && <div className={styles.error}>{error}</div>}
            <div className={styles.inputGroup}>
              <label className={styles.label} htmlFor="login-code">
                One-time code
              </label>
              <input
                id="login-code"
                className={styles.input}
                type="text"
                inputMode="numeric"
                pattern="\d{6}"
                maxLength={6}
                placeholder="123456"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                required
                autoComplete="one-time-code"
                autoFocus
              />
            </div>
            <button
              type="submit"
              className={styles.submitBtn}
              disabled={submitting}
            >
              {submitting ? "Verifying…" : "Verify code"}
            </button>
            <button
              type="button"
              className={styles.testBtn}
              onClick={() => {
                setStep("email");
                setCode("");
                setError(null);
              }}
            >
              Use a different email
            </button>
          </form>
        )}

        {step === "name" && (
          <form className={styles.form} onSubmit={handleSubmitName}>
            {error && <div className={styles.error}>{error}</div>}
            <div className={styles.inputGroup}>
              <label className={styles.label} htmlFor="login-name">
                Your name
              </label>
              <input
                id="login-name"
                className={styles.input}
                type="text"
                placeholder="Priya Verma"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                autoComplete="name"
                autoFocus
              />
            </div>
            <button
              type="submit"
              className={styles.submitBtn}
              disabled={submitting}
            >
              {submitting ? "Creating account…" : "Continue"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Run type check + lint**

```bash
cd frontend
npm run build 2>&1 | head -60
npm run lint
```
Expected: no errors (zero TypeScript errors, zero ESLint errors).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/login/page.tsx
git commit -m "feat: rewrite login page as 3-step email→code→name OTP flow"
```

---

## Task 15: Docs Update

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/development_guide.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update auth row in docs/architecture.md**

Find the "Firebase Admin SDK" mention in the tech stack table and change the Auth row to:

```markdown
| Auth | Self-hosted email-OTP + stateless JWT (PyJWT HS256, Resend) |
```

- [ ] **Step 2: Update docs/development_guide.md**

Find the "Firebase setup" section and replace it with:

```markdown
## Auth Setup (Email OTP)

No external auth service required. The backend generates 6-digit OTP codes and
emails them via Resend (or prints to stdout in dev mode).

### Local dev

In `backend/app/.env`, set:

```ini
EMAIL_PROVIDER=console
JWT_SECRET=<any-32-char-string>
OTP_PEPPER=<any-16-char-string>
```

With `EMAIL_PROVIDER=console`, every OTP code is printed to the backend's
stdout — no real email is sent. Copy the code from the terminal when signing in
at http://localhost:3000/login.

### Production (Resend)

1. Create a Resend account at https://resend.com, verify your sending domain.
2. Generate an API key and add to your deployment environment:

```ini
EMAIL_PROVIDER=resend
RESEND_API_KEY=re_...
RESEND_FROM_EMAIL=noreply@yourdomain.com
```

### Test accounts

After running `PYTHONPATH=src uv run python scripts/seed_database.py`, sign in with:

| Role     | Email                        |
|----------|------------------------------|
| Admin    | admin@khanabazaar.dev        |
| Seller   | seller@khanabazaar.dev       |
| Customer | customer@khanabazaar.dev     |

Codes appear in backend stdout (console provider).
```

- [ ] **Step 3: Update CLAUDE.md**

In the tech stack table, change the Auth row from:

```markdown
| Auth | Firebase Admin SDK (phone OTP + email) |
```

to:

```markdown
| Auth | Self-hosted email-OTP + JWT (PyJWT HS256, Resend) |
```

- [ ] **Step 4: Commit**

```bash
git add docs/architecture.md docs/development_guide.md CLAUDE.md
git commit -m "docs: update auth documentation — Firebase → self-hosted email-OTP"
```

---

## End-to-End Verification

After all tasks complete:

```bash
# 1. Infrastructure
docker-compose up -d

# 2. Backend
cd backend/app
uv sync
uv run alembic upgrade head
PYTHONPATH=src uv run python scripts/seed_database.py
uv run uvicorn app.main:app --reload &

# 3. Frontend
cd frontend
npm install
npm run dev &
```

**Scenarios to verify manually:**

- New signup: visit http://localhost:3000/login → enter a fresh email → "Send code" → copy the 6-digit code from backend stdout → enter code → name prompt appears → enter name → lands on `/stores` with `kb_token` in browser localStorage.
- Returning user: repeat with the same email → code → straight through to `/stores`.
- Admin login: use `admin@khanabazaar.dev` → code from stdout → lands on `/admin`.
- Seller login: `seller@khanabazaar.dev` → lands on `/seller`.
- Role gating: customer sees cart icon + add-to-cart buttons; seller/admin do not.
- Wrong code ×5: returns `too_many_attempts`.
- Rapid resend: second request within 60 s returns `rate_limited`.
- JWT in localStorage: `localStorage.getItem("kb_token")` returns the JWT; reload keeps you logged in.

**Automated checks:**

```bash
# Backend
cd backend/app
uv run pytest -v                 # all tests green
uv run ruff check .              # no lint errors
uv run mypy .                    # no type errors

# Frontend
cd frontend
npm run lint                     # no ESLint errors
npm run build                    # TypeScript compile passes
```
