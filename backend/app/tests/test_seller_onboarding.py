# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest

VALID = {
    "store_name": "Sharma Kirana",
    "contact_phone": "+919812345678",
    "contact_email": "sharma@example.com",
    "contact_address": "12 MG Road, Pune 411001",
    "preferred_categories": "Grocery, Dairy",
    "area_lat": 18.5204,
    "area_lng": 73.8567,
    "area_label": "Pune",
    "source": "home",
}


@pytest.mark.asyncio
async def test_submit_creates_request(client):
    r = await client.post("/api/v1/seller-onboarding-requests", json=VALID)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["store_name"] == "Sharma Kirana"
    assert body["status"] == "new"
    assert body["submitted_by_user_id"] is None
    # phone/email normalized + stored
    assert body["contact_phone"] == "+919812345678"
    assert body["contact_email"] == "sharma@example.com"


@pytest.mark.asyncio
async def test_submit_normalizes_phone_and_email(client):
    payload = {
        **VALID,
        "contact_phone": "+91 98123-45678",
        "contact_email": "Sharma@Example.COM",
    }
    r = await client.post("/api/v1/seller-onboarding-requests", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["contact_phone"] == "+919812345678"
    assert body["contact_email"] == "sharma@example.com"


@pytest.mark.asyncio
async def test_submit_rejects_bad_phone(client):
    # Passes the schema's min_length=8 but is not a valid Indian mobile, so it
    # reaches the handler's normalize_phone guard (not pydantic length).
    bad = {**VALID, "contact_phone": "+12025550123"}
    r = await client.post("/api/v1/seller-onboarding-requests", json=bad)
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "phone_invalid"


@pytest.mark.asyncio
async def test_submit_rejects_bad_email(client):
    bad = {**VALID, "contact_email": "nope"}
    r = await client.post("/api/v1/seller-onboarding-requests", json=bad)
    assert r.status_code == 422  # pydantic EmailStr


@pytest.mark.asyncio
async def test_submit_requires_store_name(client):
    bad = {k: v for k, v in VALID.items() if k != "store_name"}
    r = await client.post("/api/v1/seller-onboarding-requests", json=bad)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_submit_rate_limited_after_five(client):
    for _ in range(5):
        ok = await client.post("/api/v1/seller-onboarding-requests", json=VALID)
        assert ok.status_code == 201
    blocked = await client.post("/api/v1/seller-onboarding-requests", json=VALID)
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["error"] == "rate_limited"
