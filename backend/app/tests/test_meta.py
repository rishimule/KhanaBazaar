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
