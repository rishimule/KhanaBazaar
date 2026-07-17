# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.auth_session import AuthSession
from app.models.base import User, UserRole


class SessionError(Exception):
    """Base: a refresh attempt could not be honored; the caller returns 401."""


class SessionInvalid(SessionError):
    """No live session matched, or the session is expired/revoked."""


class SessionReuseDetected(SessionError):
    """A rotated-out token was replayed after the grace window; the session has
    been revoked as a compromise response."""


def client_meta(request: Request) -> tuple[str, str | None]:
    """Extract (user_agent, client_ip) from a request for session bookkeeping.
    Cloud Run / Firebase place the real client IP first in X-Forwarded-For."""
    ua = request.headers.get("user-agent", "")
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        ip: str | None = xff.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else None
    return ua, ip


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def device_label(user_agent: str) -> str:
    """Best-effort human label from a User-Agent string, e.g. 'Chrome on
    Windows'. Deliberately tiny — no UA-parsing dependency."""
    ua = user_agent or ""
    if "Edg/" in ua:
        browser = "Edge"
    elif "OPR/" in ua or "Opera" in ua:
        browser = "Opera"
    elif "Chrome/" in ua:
        browser = "Chrome"
    elif "Firefox/" in ua:
        browser = "Firefox"
    elif "Safari/" in ua:
        browser = "Safari"
    else:
        browser = "Browser"
    if "Windows" in ua:
        os_name = "Windows"
    elif "Android" in ua:
        os_name = "Android"
    elif "iPhone" in ua or "iPad" in ua or "iOS" in ua:
        os_name = "iOS"
    elif "Mac OS X" in ua or "Macintosh" in ua:
        os_name = "macOS"
    elif "Linux" in ua:
        os_name = "Linux"
    else:
        os_name = "device"
    if browser == "Browser" and os_name == "device":
        return "Unknown device"
    return f"{browser} on {os_name}"


def _durations_for_role(
    role: UserRole, trusted: bool
) -> tuple[timedelta | None, timedelta]:
    """Return (idle_timeout, absolute_cap). idle is None for untrusted sessions
    (no sliding — they hard-expire at the absolute cap)."""
    if not trusted:
        return None, timedelta(hours=settings.SESSION_UNTRUSTED_TTL_HOURS)
    if role == UserRole.Admin:
        return (
            timedelta(days=settings.SESSION_ADMIN_IDLE_DAYS),
            timedelta(days=settings.SESSION_ADMIN_MAX_DAYS),
        )
    if role == UserRole.Seller:
        return (
            timedelta(days=settings.SESSION_SELLER_IDLE_DAYS),
            timedelta(days=settings.SESSION_SELLER_MAX_DAYS),
        )
    return (
        timedelta(days=settings.SESSION_CUSTOMER_IDLE_DAYS),
        timedelta(days=settings.SESSION_CUSTOMER_MAX_DAYS),
    )


async def create_session(
    session: AsyncSession,
    *,
    user: User,
    trusted: bool,
    user_agent: str = "",
    ip: str | None = None,
) -> tuple[AuthSession, str]:
    """Create a new auth_session row for a fresh login. Returns (row, raw
    refresh token). The raw token is returned once and never stored."""
    assert user.id is not None
    now = datetime.now(timezone.utc)
    _idle, absolute = _durations_for_role(user.role, trusted)
    raw = generate_refresh_token()
    row = AuthSession(
        user_id=user.id,
        refresh_token_hash=hash_token(raw),
        trusted=trusted,
        last_used_at=now,
        absolute_expires_at=now + absolute,
        device_label=device_label(user_agent),
        user_agent=user_agent[:500],
        ip=ip,
    )
    session.add(row)
    await session.flush()
    return row, raw


async def rotate_session(
    session: AsyncSession,
    *,
    raw_refresh_token: str,
    user_agent: str = "",
    ip: str | None = None,
) -> tuple[User, AuthSession, str]:
    """Validate a presented refresh token and rotate it. Returns
    (user, row, new raw refresh token). Raises SessionReuseDetected /
    SessionInvalid on failure. Flushes but does not commit — the caller commits
    (including after SessionReuseDetected, to persist the revocation)."""
    now = datetime.now(timezone.utc)
    h = hash_token(raw_refresh_token)

    row = (
        await session.exec(
            select(AuthSession)
            .where(AuthSession.refresh_token_hash == h)
            .with_for_update()
        )
    ).first()

    if row is None:
        # Maybe a rotated-out (previous) token: tolerate within grace, else
        # treat as replay/theft.
        prev = (
            await session.exec(
                select(AuthSession)
                .where(AuthSession.prev_token_hash == h)
                .with_for_update()
            )
        ).first()
        if prev is None:
            # Not the current hash, not the immediate previous hash. Check the
            # bounded history of older rotated-out hashes: these are ALWAYS
            # older than `prev`, so a match here is always "after grace" —
            # genuine reuse of a stale-but-once-issued token. A hash that
            # matches nothing stored anywhere is a forged/garbage token and
            # MUST NOT revoke anything (no session-revocation DoS).
            hist_row = (
                await session.exec(
                    select(AuthSession)
                    .where(AuthSession.rotated_hashes.contains([h]))  # type: ignore[attr-defined]
                    .with_for_update()
                )
            ).first()
            if hist_row is not None:
                if hist_row.revoked_at is None:
                    hist_row.revoked_at = now
                    session.add(hist_row)
                    await session.flush()
                raise SessionReuseDetected()
            raise SessionInvalid()
        grace = timedelta(seconds=settings.REFRESH_TOKEN_REUSE_GRACE_SECONDS)
        if (
            prev.revoked_at is not None
            or prev.prev_rotated_at is None
            or now - prev.prev_rotated_at > grace
        ):
            if prev.revoked_at is None:
                prev.revoked_at = now
                session.add(prev)
                await session.flush()
            raise SessionReuseDetected()
        row = prev  # within grace → tolerate; rotate from current below

    user = (
        await session.exec(select(User).where(User.id == row.user_id))
    ).first()
    if user is None or not user.is_active:
        raise SessionInvalid()

    idle, _absolute = _durations_for_role(user.role, row.trusted)
    if row.revoked_at is not None or now > row.absolute_expires_at:
        raise SessionInvalid()
    if idle is not None and now - row.last_used_at > idle:
        raise SessionInvalid()

    new_raw = generate_refresh_token()
    if row.prev_token_hash is not None:
        history = list(row.rotated_hashes or [])
        history.insert(0, row.prev_token_hash)  # displaced prev becomes gen-2
        row.rotated_hashes = history[: settings.SESSION_REUSE_HISTORY_SIZE]
    row.prev_token_hash = row.refresh_token_hash
    row.prev_rotated_at = now
    row.refresh_token_hash = hash_token(new_raw)
    row.last_used_at = now
    if user_agent:
        row.user_agent = user_agent[:500]
        row.device_label = device_label(user_agent)
    if ip:
        row.ip = ip
    session.add(row)
    await session.flush()
    return user, row, new_raw


async def revoke_session(
    session: AsyncSession, *, auth_session_id: int, user_id: int
) -> bool:
    """Revoke one session owned by user_id. Returns True if a live row was
    revoked; False if not found / not owned / already revoked."""
    row = (
        await session.exec(
            select(AuthSession).where(
                AuthSession.id == auth_session_id,
                AuthSession.user_id == user_id,
            )
        )
    ).first()
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = datetime.now(timezone.utc)
    session.add(row)
    await session.flush()
    return True


async def revoke_all_sessions(
    session: AsyncSession,
    *,
    user_id: int,
    except_auth_session_id: int | None = None,
) -> int:
    """Revoke every live (non-revoked) session owned by user_id, optionally
    sparing one (e.g. the caller's current session on 'log out everywhere').
    Returns the number of sessions revoked. Flushes; the caller commits."""
    now = datetime.now(timezone.utc)
    rows = (
        await session.exec(
            select(AuthSession).where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),  # type: ignore[union-attr]
            )
        )
    ).all()
    count = 0
    for row in rows:
        if except_auth_session_id is not None and row.id == except_auth_session_id:
            continue
        row.revoked_at = now
        session.add(row)
        count += 1
    if count:
        await session.flush()
    return count


async def revoke_session_by_token(
    session: AsyncSession, *, raw_refresh_token: str
) -> bool:
    """Revoke the session identified by a presented refresh token (logout).
    Idempotent: returns False if no live session matches."""
    h = hash_token(raw_refresh_token)
    row = (
        await session.exec(
            select(AuthSession).where(AuthSession.refresh_token_hash == h)
        )
    ).first()
    if row is None:
        row = (
            await session.exec(
                select(AuthSession).where(AuthSession.prev_token_hash == h)
            )
        ).first()
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = datetime.now(timezone.utc)
    session.add(row)
    await session.flush()
    return True
