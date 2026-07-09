# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest

VALID = {
    "target_role": "customer",
    "invitee_name": "Asha Rao",
    "invitee_email": "asha@example.com",
    "location_state": "Maharashtra",
    "location_area": "Kothrud, Pune",
}


async def _submit(client, headers):
    r = await client.post("/api/v1/referrals", json=VALID, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_admin_list_and_approve(client, customer_auth_headers, admin_auth_headers):
    rid = await _submit(client, customer_auth_headers)
    lst = await client.get(
        "/api/v1/admin/referrals?status=pending_review", headers=admin_auth_headers
    )
    assert lst.status_code == 200
    assert lst.json()["total"] >= 1
    ap = await client.post(
        f"/api/v1/admin/referrals/{rid}/approve", headers=admin_auth_headers
    )
    assert ap.status_code == 200, ap.text
    assert ap.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_admin_reject_requires_reason(client, customer_auth_headers, admin_auth_headers):
    rid = await _submit(client, customer_auth_headers)
    bad = await client.post(
        f"/api/v1/admin/referrals/{rid}/reject", json={}, headers=admin_auth_headers
    )
    assert bad.status_code == 422
    ok = await client.post(
        f"/api/v1/admin/referrals/{rid}/reject",
        json={"reason": "spam"},
        headers=admin_auth_headers,
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "rejected"
    assert ok.json()["rejection_reason"] == "spam"


@pytest.mark.asyncio
async def test_approve_twice_conflict(client, customer_auth_headers, admin_auth_headers):
    rid = await _submit(client, customer_auth_headers)
    await client.post(f"/api/v1/admin/referrals/{rid}/approve", headers=admin_auth_headers)
    again = await client.post(
        f"/api/v1/admin/referrals/{rid}/approve", headers=admin_auth_headers
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_admin_list_requires_admin(client):
    r = await client.get("/api/v1/admin/referrals")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_settings_toggle_autoapproves(client, customer_auth_headers, admin_auth_headers):
    patch = await client.patch(
        "/api/v1/admin/referrals/settings",
        json={"require_admin_approval": False},
        headers=admin_auth_headers,
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["require_admin_approval"] is False
    r = await client.post("/api/v1/referrals", json=VALID, headers=customer_auth_headers)
    assert r.status_code == 201
    assert r.json()["status"] == "approved"
