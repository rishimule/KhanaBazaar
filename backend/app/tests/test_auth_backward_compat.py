# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from httpx import AsyncClient

from app.core.config import settings
from app.models.base import User, UserRole


async def test_legacy_sidless_24h_token_still_authorizes_me(
    client: AsyncClient, session: Any
) -> None:
    """A pre-rollout token (no `sid`, 24h exp) must still authorize /auth/me —
    existing logged-in users are not force-logged-out on deploy."""
    user = User(email="legacy@x.test", role=UserRole.Customer)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    now = datetime.now(timezone.utc)
    legacy = jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role.value,
            "iat": now,
            "exp": now + timedelta(hours=24),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {legacy}"}
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "legacy@x.test"


async def test_full_rotation_chain_then_logout(
    client: AsyncClient, session: Any
) -> None:
    from app.services.sessions import create_session

    user = User(email="chain@x.test", role=UserRole.Seller)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    _row, raw = await create_session(session, user=user, trusted=True)
    await session.commit()

    # Rotate three times.
    token = raw
    for _ in range(3):
        r = await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
        assert r.status_code == 200
        token = r.json()["refresh_token"]

    # Logout kills the session; the latest token no longer refreshes.
    out = await client.post("/api/v1/auth/logout", json={"refresh_token": token})
    assert out.status_code == 200
    dead = await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
    assert dead.status_code == 401
