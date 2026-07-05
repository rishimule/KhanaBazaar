# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_settings_returns_defaults(client: AsyncClient, admin_auth_headers) -> None:
    r = await client.get("/api/v1/admin/fees/settings", headers=admin_auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["grace_period_days"] == 2
    assert body["expiry_reminder_start_days"] == 7
    assert body["gstin"] is None


@pytest.mark.asyncio
async def test_patch_settings_persists(client: AsyncClient, admin_auth_headers) -> None:
    r = await client.patch(
        "/api/v1/admin/fees/settings",
        headers=admin_auth_headers,
        json={"grace_period_days": 0, "gstin": "27ABCDE1234F1Z5", "upi_id": "kb@upi"},
    )
    assert r.status_code == 200
    assert r.json()["grace_period_days"] == 0
    # Re-read: value survived and no duplicate row was created.
    r2 = await client.get("/api/v1/admin/fees/settings", headers=admin_auth_headers)
    assert r2.json()["gstin"] == "27ABCDE1234F1Z5"
    assert r2.json()["upi_id"] == "kb@upi"


@pytest.mark.asyncio
async def test_settings_requires_admin(client: AsyncClient) -> None:
    r = await client.get("/api/v1/admin/fees/settings")
    assert r.status_code in (401, 403)
