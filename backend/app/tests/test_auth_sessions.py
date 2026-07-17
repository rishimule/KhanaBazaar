# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Any

from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.base import User, UserRole


async def _user_with_session(session: Any, role: UserRole = UserRole.Customer):
    from app.services.sessions import create_session

    user = User(email=f"sess-{role.value}@x.test", role=role)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    row, raw = await create_session(session, user=user, trusted=True)
    await session.commit()
    token = create_access_token(user, sid=row.id)
    return user, row, raw, token


async def test_list_sessions_marks_current(client: AsyncClient, session: Any) -> None:
    user, row, _raw, token = await _user_with_session(session)
    from app.services.sessions import create_session

    other, _o = await create_session(session, user=user, trusted=True)
    await session.commit()

    resp = await client.get(
        "/api/v1/auth/sessions", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = {s["id"]: s for s in resp.json()}
    assert data[row.id]["current"] is True
    assert data[other.id]["current"] is False
    assert "device_label" in data[row.id] and "last_used_at" in data[row.id]


async def test_delete_session_revokes_and_404s_for_others(
    client: AsyncClient, session: Any
) -> None:
    user, row, raw, token = await _user_with_session(session)
    from app.services.sessions import create_session

    victim, _v = await create_session(session, user=user, trusted=True)
    await session.commit()

    # Revoke the other session.
    d = await client.delete(
        f"/api/v1/auth/sessions/{victim.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert d.status_code == 204

    # A different user cannot revoke this user's session.
    other_user, _r2, _raw2, other_token = await _user_with_session(
        session, UserRole.Seller
    )
    d2 = await client.delete(
        f"/api/v1/auth/sessions/{row.id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert d2.status_code == 404
    assert d2.json()["detail"]["error"] == "session_not_found"


async def test_revoke_all_spares_current(client: AsyncClient, session: Any) -> None:
    user, row, raw, token = await _user_with_session(session)
    from app.services.sessions import create_session

    await create_session(session, user=user, trusted=True)
    await create_session(session, user=user, trusted=True)
    await session.commit()

    resp = await client.post(
        "/api/v1/auth/sessions/revoke-all",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["revoked"] == 2

    # The current session still refreshes; the list now shows only it.
    lst = await client.get(
        "/api/v1/auth/sessions", headers={"Authorization": f"Bearer {token}"}
    )
    ids = [s["id"] for s in lst.json()]
    assert ids == [row.id]
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": raw})
    assert r.status_code == 200


async def test_list_excludes_revoked(client: AsyncClient, session: Any) -> None:
    user, row, _raw, token = await _user_with_session(session)
    await client.post(
        "/api/v1/auth/sessions/revoke-all",
        headers={"Authorization": f"Bearer {token}"},
    )
    # revoke-all spared current; now revoke current explicitly then list.
    await client.delete(
        f"/api/v1/auth/sessions/{row.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    lst = await client.get(
        "/api/v1/auth/sessions", headers={"Authorization": f"Bearer {token}"}
    )
    assert lst.status_code == 200
    assert lst.json() == []
