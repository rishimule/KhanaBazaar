# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timedelta, timezone
from typing import Any

from httpx import AsyncClient
from sqlmodel import select

from app.models.base import User, UserRole


async def _seed_session(session: Any, trusted: bool = True) -> tuple[User, str]:
    from app.services.sessions import create_session

    user = User(email=f"r-{datetime.now().timestamp()}@x.test", role=UserRole.Customer)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    _row, raw = await create_session(session, user=user, trusted=trusted)
    await session.commit()
    return user, raw


async def test_refresh_returns_new_tokens_and_rotates(
    client: AsyncClient, session: Any
) -> None:
    _user, raw = await _seed_session(session)
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": raw})
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"]
    assert data["refresh_token"] and data["refresh_token"] != raw
    assert data["expires_in"] == 15 * 60
    # The NEW token definitely works.
    resp2 = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]}
    )
    assert resp2.status_code == 200


async def test_refresh_unknown_token_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": "bogus-token-value"}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "invalid_session"


async def test_refresh_reuse_after_grace_revokes_session(
    client: AsyncClient, session: Any
) -> None:
    from app.models.auth_session import AuthSession

    _user, raw = await _seed_session(session)
    # First refresh so `raw` becomes previous.
    first = await client.post("/api/v1/auth/refresh", json={"refresh_token": raw})
    assert first.status_code == 200

    # Age the rotation past the grace window.
    row = (await session.exec(select(AuthSession))).one()
    row.prev_rotated_at = datetime.now(timezone.utc) - timedelta(seconds=120)
    session.add(row)
    await session.commit()

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": raw})
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "session_revoked"

    # Revocation persisted. Re-read from the DB (the fixture session has the
    # pre-revoke object cached with expire_on_commit=False).
    await session.refresh(row)
    assert row.revoked_at is not None


async def test_logout_revokes_session(client: AsyncClient, session: Any) -> None:
    _user, raw = await _seed_session(session)
    out = await client.post("/api/v1/auth/logout", json={"refresh_token": raw})
    assert out.status_code == 200
    assert out.json()["ok"] is True
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": raw})
    assert resp.status_code == 401
