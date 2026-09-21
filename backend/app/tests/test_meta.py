# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from httpx import ASGITransport, AsyncClient

from app import app


@pytest.mark.asyncio
async def test_indian_states_endpoint_returns_36_entries() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/meta/indian-states")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["states"]) == 36
    assert "Maharashtra" in data["states"]
    assert "Delhi" in data["states"]


@pytest.mark.asyncio
async def test_meta_health_endpoint_returns_ok() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/meta/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "environment" in body


@pytest.mark.asyncio
async def test_public_config_reports_phone_otp_enabled_by_default() -> None:
    """Unauthenticated: clients need it before any OTP call to label the
    'Send code' button honestly."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/meta/public-config")
    assert resp.status_code == 200, resp.text
    assert resp.json()["phone_otp_enabled"] is True


@pytest.mark.asyncio
async def test_public_config_reflects_disabled_phone_otp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "PHONE_OTP_ENABLED", False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/meta/public-config")
    assert resp.status_code == 200, resp.text
    assert resp.json()["phone_otp_enabled"] is False
