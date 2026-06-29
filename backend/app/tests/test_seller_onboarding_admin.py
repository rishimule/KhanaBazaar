# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest

VALID = {
    "store_name": "Sharma Kirana",
    "contact_phone": "+919812345678",
    "contact_email": "sharma@example.com",
    "contact_address": "12 MG Road, Pune",
}


@pytest.mark.asyncio
async def test_admin_list_returns_submissions(client, admin_auth_headers):
    await client.post("/api/v1/seller-onboarding-requests", json=VALID)
    r = await client.get(
        "/api/v1/admin/onboarding-requests", headers=admin_auth_headers
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1
    assert body["items"][0]["store_name"] == "Sharma Kirana"


@pytest.mark.asyncio
async def test_admin_list_requires_admin(client):
    r = await client.get("/api/v1/admin/onboarding-requests")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_list_filters_by_status(client, admin_auth_headers):
    await client.post("/api/v1/seller-onboarding-requests", json=VALID)
    r = await client.get(
        "/api/v1/admin/onboarding-requests?status=contacted",
        headers=admin_auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["total"] == 0  # the only row is 'new'


@pytest.mark.asyncio
async def test_admin_list_search_by_store_name(client, admin_auth_headers):
    await client.post("/api/v1/seller-onboarding-requests", json=VALID)
    r = await client.get(
        "/api/v1/admin/onboarding-requests?q=sharma",
        headers=admin_auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_admin_patch_updates_status(client, admin_auth_headers):
    created = await client.post("/api/v1/seller-onboarding-requests", json=VALID)
    rid = created.json()["id"]
    r = await client.patch(
        f"/api/v1/admin/onboarding-requests/{rid}",
        json={"status": "contacted"},
        headers=admin_auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "contacted"


@pytest.mark.asyncio
async def test_admin_patch_unknown_id_404(client, admin_auth_headers):
    r = await client.patch(
        "/api/v1/admin/onboarding-requests/999999",
        json={"status": "contacted"},
        headers=admin_auth_headers,
    )
    assert r.status_code == 404
