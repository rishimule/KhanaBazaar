# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_user
from app.models.base import User, UserRole
from app.models.profile import CustomerProfile

mock_admin = User(id=811, email="ca-admin@kb.com", role=UserRole.Admin, is_active=True)
mock_customer = User(id=812, email="ca-cust@kb.com", role=UserRole.Customer, is_active=True)


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[None, None]:
    for u in (mock_admin, mock_customer):
        session.add(User(**u.model_dump()))
    await session.flush()
    session.add(CustomerProfile(user_id=mock_customer.id, first_name="C", marketing_opt_in=True))
    await session.commit()
    yield


@pytest.fixture
def client_factory():  # noqa: ANN201
    @asynccontextmanager
    async def _make(user: User):  # noqa: ANN202
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    return _make


_DRAFT = {
    "audience": "both",
    "channels": ["in_app"],
    "title": "Launch",
    "body": "New features are live.",
}


async def test_create_draft(client_factory) -> None:
    async with client_factory(mock_admin) as ac:
        resp = await ac.post("/api/v1/admin/notifications/campaigns", json=_DRAFT)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "draft"
    assert data["audience"] == "both"


async def test_audience_count(client_factory) -> None:
    async with client_factory(mock_admin) as ac:
        created = (await ac.post("/api/v1/admin/notifications/campaigns", json=_DRAFT)).json()
        resp = await ac.post(
            f"/api/v1/admin/notifications/campaigns/{created['id']}/audience-count"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["customers"] >= 1 and "sellers" in body


async def test_send_transitions_to_sent(client_factory) -> None:
    async with client_factory(mock_admin) as ac:
        created = (await ac.post("/api/v1/admin/notifications/campaigns", json=_DRAFT)).json()
        resp = await ac.post(
            f"/api/v1/admin/notifications/campaigns/{created['id']}/send"
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "sent"


async def test_send_twice_conflicts(client_factory) -> None:
    async with client_factory(mock_admin) as ac:
        created = (await ac.post("/api/v1/admin/notifications/campaigns", json=_DRAFT)).json()
        await ac.post(f"/api/v1/admin/notifications/campaigns/{created['id']}/send")
        resp = await ac.post(f"/api/v1/admin/notifications/campaigns/{created['id']}/send")
    assert resp.status_code == 409


async def test_edit_sent_conflicts(client_factory) -> None:
    async with client_factory(mock_admin) as ac:
        created = (await ac.post("/api/v1/admin/notifications/campaigns", json=_DRAFT)).json()
        await ac.post(f"/api/v1/admin/notifications/campaigns/{created['id']}/send")
        resp = await ac.patch(
            f"/api/v1/admin/notifications/campaigns/{created['id']}", json={"title": "Nope"}
        )
    assert resp.status_code == 409


async def test_invalid_channels_rejected(client_factory) -> None:
    async with client_factory(mock_admin) as ac:
        resp = await ac.post(
            "/api/v1/admin/notifications/campaigns",
            json={**_DRAFT, "channels": ["email"]},  # missing in_app
        )
    assert resp.status_code == 422


async def test_non_http_cta_url_rejected(client_factory) -> None:
    async with client_factory(mock_admin) as ac:
        resp = await ac.post(
            "/api/v1/admin/notifications/campaigns",
            json={**_DRAFT, "cta_url": "javascript:alert(1)"},
        )
    assert resp.status_code == 422


async def test_non_admin_forbidden(client_factory) -> None:
    async with client_factory(mock_customer) as ac:
        resp = await ac.get("/api/v1/admin/notifications/campaigns")
    assert resp.status_code in (401, 403)
