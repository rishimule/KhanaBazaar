# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from httpx import AsyncClient

from app.core.config import settings


@pytest.fixture
def enable_dev_otps(monkeypatch):
    monkeypatch.setattr(settings, "EXPOSE_DEV_OTPS", True)
    monkeypatch.setattr(settings, "DEV_LOGS_USERNAME", "devuser")
    monkeypatch.setattr(settings, "DEV_LOGS_PASSWORD", "devpass")


async def test_returns_404_when_disabled(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "EXPOSE_DEV_OTPS", False)
    resp = await client.get("/api/v1/dev/otps")  # no creds
    assert resp.status_code == 404


async def test_requires_basic_auth(client: AsyncClient, enable_dev_otps):
    resp = await client.get("/api/v1/dev/otps")
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate", "").lower().startswith("basic")


async def test_rejects_wrong_credentials(client: AsyncClient, enable_dev_otps):
    resp = await client.get("/api/v1/dev/otps", auth=("devuser", "wrong"))
    assert resp.status_code == 401


async def test_returns_recorded_otps(client: AsyncClient, enable_dev_otps):
    # Trigger an OTP so the inbox has an entry (capture is enabled).
    r1 = await client.post("/api/v1/auth/otp/request", json={"email": "x@y.com"})
    assert r1.status_code == 200
    resp = await client.get("/api/v1/dev/otps", auth=("devuser", "devpass"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["otps"][0]["to"] == "x@y.com"
    assert len(body["otps"][0]["code"]) == 6
