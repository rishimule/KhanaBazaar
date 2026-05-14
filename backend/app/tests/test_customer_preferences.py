# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_customer
from app.models.base import User, UserRole
from app.models.profile import CustomerProfile

pytestmark = pytest.mark.asyncio


class _Ids:
    def __init__(self, **kwargs: int | str) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


async def _make_customer(session: AsyncSession, email: str = "pref@example.com") -> _Ids:
    user = User(email=email, role=UserRole.Customer, is_active=True)
    session.add(user)
    await session.flush()
    assert user.id is not None
    profile = CustomerProfile(user_id=user.id, first_name="Pref")
    session.add(profile)
    await session.flush()
    assert profile.id is not None
    return _Ids(user_id=user.id, profile_id=profile.id, email=email)


def _user_for(ids: _Ids) -> User:
    return User(
        id=ids.user_id,  # type: ignore[attr-defined]
        email=ids.email,  # type: ignore[attr-defined]
        role=UserRole.Customer,
        is_active=True,
    )


async def test_patch_preferences_updates_fields(client: AsyncClient, session: AsyncSession):
    ids = await _make_customer(session)
    await session.commit()
    app.dependency_overrides[get_current_customer] = lambda: _user_for(ids)
    try:
        r = await client.patch(
            "/api/v1/customers/me/preferences",
            json={
                "preferred_language": "hi",
                "marketing_opt_in": True,
                "notify_order_email": False,
                "notify_order_sms": True,
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["preferred_language"] == "hi"
    assert data["marketing_opt_in"] is True
    assert data["notify_order_email"] is False
    assert data["notify_order_sms"] is True


async def test_patch_preferences_rejects_unknown_language(client: AsyncClient, session: AsyncSession):
    ids = await _make_customer(session)
    await session.commit()
    app.dependency_overrides[get_current_customer] = lambda: _user_for(ids)
    try:
        r = await client.patch(
            "/api/v1/customers/me/preferences",
            json={"preferred_language": "fr"},
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 422


async def test_patch_preferences_partial_preserves_other_fields(
    client: AsyncClient, session: AsyncSession
):
    ids = await _make_customer(session)
    await session.commit()
    app.dependency_overrides[get_current_customer] = lambda: _user_for(ids)
    try:
        await client.patch(
            "/api/v1/customers/me/preferences",
            json={"marketing_opt_in": True},
        )
        r = await client.patch(
            "/api/v1/customers/me/preferences",
            json={"notify_order_sms": True},
        )
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["marketing_opt_in"] is True
    assert data["notify_order_sms"] is True
