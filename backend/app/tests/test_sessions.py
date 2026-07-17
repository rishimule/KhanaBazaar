# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.models.base import User, UserRole


async def _make_user(session: Any, role: UserRole = UserRole.Customer) -> User:
    user = User(email=f"u-{role.value}@x.test", role=role)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_create_session_untrusted_caps_at_24h(session: Any) -> None:
    from app.services.sessions import create_session

    user = await _make_user(session)
    row, raw = await create_session(session, user=user, trusted=False)
    await session.commit()
    delta = row.absolute_expires_at - row.created_at
    assert timedelta(hours=23) < delta < timedelta(hours=25)
    assert row.trusted is False
    assert raw and row.refresh_token_hash != raw


async def test_create_session_trusted_customer_180d(session: Any) -> None:
    from app.services.sessions import create_session

    user = await _make_user(session, UserRole.Customer)
    row, _raw = await create_session(session, user=user, trusted=True)
    await session.commit()
    delta = row.absolute_expires_at - row.created_at
    assert timedelta(days=179) < delta < timedelta(days=181)


async def test_create_session_trusted_admin_30d(session: Any) -> None:
    from app.services.sessions import create_session

    user = await _make_user(session, UserRole.Admin)
    row, _raw = await create_session(session, user=user, trusted=True)
    await session.commit()
    delta = row.absolute_expires_at - row.created_at
    assert timedelta(days=29) < delta < timedelta(days=31)


async def test_rotate_happy_path(session: Any) -> None:
    from app.services.sessions import create_session, rotate_session

    user = await _make_user(session)
    _row, raw = await create_session(session, user=user, trusted=True)
    await session.commit()

    ret_user, ret_row, new_raw = await rotate_session(
        session, raw_refresh_token=raw
    )
    await session.commit()
    assert ret_user.id == user.id
    assert new_raw != raw
    # New token works, old token no longer matches "current".
    _u2, _r2, new_raw2 = await rotate_session(session, raw_refresh_token=new_raw)
    await session.commit()
    assert new_raw2 not in (raw, new_raw)


async def test_rotate_unknown_token_raises_invalid(session: Any) -> None:
    from app.services.sessions import SessionInvalid, rotate_session

    with pytest.raises(SessionInvalid):
        await rotate_session(session, raw_refresh_token="nope-not-a-real-token")


async def test_rotate_reuse_after_grace_revokes(session: Any) -> None:
    from sqlmodel import select

    from app.models.auth_session import AuthSession
    from app.services.sessions import (
        SessionReuseDetected,
        create_session,
        rotate_session,
    )

    user = await _make_user(session)
    row, raw = await create_session(session, user=user, trusted=True)
    await session.commit()
    row_id = row.id

    # Rotate once so `raw` becomes the previous token.
    await rotate_session(session, raw_refresh_token=raw)
    await session.commit()

    # Force the rotation to be older than the grace window.
    reloaded = (
        await session.exec(select(AuthSession).where(AuthSession.id == row_id))
    ).one()
    reloaded.prev_rotated_at = datetime.now(timezone.utc) - timedelta(seconds=120)
    session.add(reloaded)
    await session.commit()

    # Replaying the old token now looks like theft → revoke the session.
    with pytest.raises(SessionReuseDetected):
        await rotate_session(session, raw_refresh_token=raw)
    await session.commit()

    reloaded = (
        await session.exec(select(AuthSession).where(AuthSession.id == row_id))
    ).one()
    assert reloaded.revoked_at is not None


async def test_rotate_prev_within_grace_tolerated(session: Any) -> None:
    from app.services.sessions import create_session, rotate_session

    user = await _make_user(session)
    _row, raw = await create_session(session, user=user, trusted=True)
    await session.commit()

    # First rotation (e.g. another tab) — `raw` becomes previous, rotated just now.
    await rotate_session(session, raw_refresh_token=raw)
    await session.commit()

    # Replaying `raw` immediately (within 30s) is tolerated: returns a fresh
    # token, does not raise.
    _u, row2, new_raw = await rotate_session(session, raw_refresh_token=raw)
    await session.commit()
    assert new_raw and row2.revoked_at is None


async def test_rotate_absolute_expiry_rejected(session: Any) -> None:
    from sqlmodel import select

    from app.models.auth_session import AuthSession
    from app.services.sessions import SessionInvalid, create_session, rotate_session

    user = await _make_user(session)
    row, raw = await create_session(session, user=user, trusted=True)
    await session.commit()
    reloaded = (
        await session.exec(select(AuthSession).where(AuthSession.id == row.id))
    ).one()
    reloaded.absolute_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    session.add(reloaded)
    await session.commit()
    with pytest.raises(SessionInvalid):
        await rotate_session(session, raw_refresh_token=raw)


async def test_rotate_idle_expiry_rejected(session: Any) -> None:
    from sqlmodel import select

    from app.models.auth_session import AuthSession
    from app.services.sessions import SessionInvalid, create_session, rotate_session

    user = await _make_user(session, UserRole.Customer)
    row, raw = await create_session(session, user=user, trusted=True)
    await session.commit()
    reloaded = (
        await session.exec(select(AuthSession).where(AuthSession.id == row.id))
    ).one()
    # Customer idle is 30 days; push last_used 31 days back.
    reloaded.last_used_at = datetime.now(timezone.utc) - timedelta(days=31)
    session.add(reloaded)
    await session.commit()
    with pytest.raises(SessionInvalid):
        await rotate_session(session, raw_refresh_token=raw)


async def test_rotate_two_generation_stale_token_revokes(session: Any) -> None:
    from sqlmodel import select

    from app.models.auth_session import AuthSession
    from app.services.sessions import (
        SessionReuseDetected,
        create_session,
        rotate_session,
    )

    user = await _make_user(session)
    row, raw = await create_session(session, user=user, trusted=True)
    await session.commit()
    row_id = row.id

    _u1, _r1, r1 = await rotate_session(session, raw_refresh_token=raw)
    await session.commit()
    _u2, _r2, _r2new = await rotate_session(session, raw_refresh_token=r1)
    await session.commit()

    # `raw` is now two generations stale (older than prev) — replaying it must
    # be detected as reuse and revoke the session.
    with pytest.raises(SessionReuseDetected):
        await rotate_session(session, raw_refresh_token=raw)
    await session.commit()

    reloaded = (
        await session.exec(select(AuthSession).where(AuthSession.id == row_id))
    ).one()
    assert reloaded.revoked_at is not None


async def test_rotate_garbage_token_never_revokes(session: Any) -> None:
    from sqlmodel import select

    from app.models.auth_session import AuthSession
    from app.services.sessions import (
        SessionInvalid,
        create_session,
        generate_refresh_token,
        rotate_session,
    )

    user = await _make_user(session)
    row, raw = await create_session(session, user=user, trusted=True)
    await session.commit()
    row_id = row.id

    await rotate_session(session, raw_refresh_token=raw)
    await session.commit()

    garbage = "garbage-" + generate_refresh_token()
    with pytest.raises(SessionInvalid):
        await rotate_session(session, raw_refresh_token=garbage)
    await session.commit()

    reloaded = (
        await session.exec(select(AuthSession).where(AuthSession.id == row_id))
    ).one()
    assert reloaded.revoked_at is None


async def test_rotate_history_capped(session: Any) -> None:
    from sqlmodel import select

    from app.core.config import settings
    from app.models.auth_session import AuthSession
    from app.services.sessions import (
        SessionInvalid,
        create_session,
        rotate_session,
    )

    user = await _make_user(session)
    row, raw = await create_session(session, user=user, trusted=True)
    await session.commit()
    row_id = row.id

    current = raw
    for _ in range(settings.SESSION_REUSE_HISTORY_SIZE + 2):
        _u, _r, current = await rotate_session(session, raw_refresh_token=current)
        await session.commit()

    # The original token has now been evicted past the bounded-history cap —
    # it should look unrecognized, not trigger reuse detection.
    with pytest.raises(SessionInvalid):
        await rotate_session(session, raw_refresh_token=raw)
    await session.commit()

    reloaded = (
        await session.exec(select(AuthSession).where(AuthSession.id == row_id))
    ).one()
    assert reloaded.revoked_at is None


async def test_revoke_session_and_by_token(session: Any) -> None:
    from app.services.sessions import (
        SessionInvalid,
        create_session,
        revoke_session,
        revoke_session_by_token,
        rotate_session,
    )

    user = await _make_user(session)
    row, raw = await create_session(session, user=user, trusted=True)
    await session.commit()

    assert await revoke_session(session, auth_session_id=row.id, user_id=user.id)
    await session.commit()
    with pytest.raises(SessionInvalid):
        await rotate_session(session, raw_refresh_token=raw)

    # revoke_by_token on a second session.
    row2, raw2 = await create_session(session, user=user, trusted=True)
    await session.commit()
    assert await revoke_session_by_token(session, raw_refresh_token=raw2)
    await session.commit()
    with pytest.raises(SessionInvalid):
        await rotate_session(session, raw_refresh_token=raw2)


async def test_revoke_all_sessions_spares_current(session: Any) -> None:
    from sqlmodel import select

    from app.models.auth_session import AuthSession
    from app.services.sessions import create_session, revoke_all_sessions

    user = await _make_user(session)
    keep, _k = await create_session(session, user=user, trusted=True)
    a, _a = await create_session(session, user=user, trusted=True)
    b, _b = await create_session(session, user=user, trusted=True)
    await session.commit()

    n = await revoke_all_sessions(
        session, user_id=user.id, except_auth_session_id=keep.id
    )
    await session.commit()
    assert n == 2

    rows = {
        r.id: r
        for r in (
            await session.exec(select(AuthSession).where(AuthSession.user_id == user.id))
        ).all()
    }
    assert rows[keep.id].revoked_at is None
    assert rows[a.id].revoked_at is not None
    assert rows[b.id].revoked_at is not None


async def test_revoke_all_sessions_no_except_revokes_all(session: Any) -> None:
    from app.services.sessions import create_session, revoke_all_sessions

    user = await _make_user(session)
    await create_session(session, user=user, trusted=True)
    await create_session(session, user=user, trusted=True)
    await session.commit()
    n = await revoke_all_sessions(session, user_id=user.id)
    await session.commit()
    assert n == 2
    # Idempotent: a second sweep revokes nothing (all already revoked).
    n2 = await revoke_all_sessions(session, user_id=user.id)
    await session.commit()
    assert n2 == 0
