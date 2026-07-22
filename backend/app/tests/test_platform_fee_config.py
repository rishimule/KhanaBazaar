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


@pytest.mark.asyncio
async def test_upload_fee_qr_sets_url(client: AsyncClient, admin_auth_headers) -> None:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (0, 0, 0)).save(buf, "PNG")
    r = await client.post(
        "/api/v1/admin/fees/settings/qr",
        headers=admin_auth_headers,
        files={"file": ("qr.png", buf.getvalue(), "image/png")},
    )
    assert r.status_code == 200, r.text
    url = r.json()["qr_image_url"]
    assert url and "fee-qr/" in url
    # Persisted onto the singleton settings.
    r2 = await client.get("/api/v1/admin/fees/settings", headers=admin_auth_headers)
    assert r2.json()["qr_image_url"] == url


@pytest.mark.asyncio
async def test_upload_fee_qr_rejects_non_image(client: AsyncClient, admin_auth_headers) -> None:
    r = await client.post(
        "/api/v1/admin/fees/settings/qr",
        headers=admin_auth_headers,
        files={"file": ("x.txt", b"not an image", "text/plain")},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_service_config_defaults(client: AsyncClient, admin_auth_headers, seeded_service) -> None:
    r = await client.get(
        f"/api/v1/admin/fees/services/{seeded_service.id}", headers=admin_auth_headers
    )
    assert r.status_code == 200
    body = r.json()
    assert body["config"]["freebie_enabled"] is True
    assert body["config"]["freebie_default_days"] == 30
    assert body["config"]["subscription_enabled"] is False
    assert body["plans"] == []


@pytest.mark.asyncio
async def test_patch_service_config(client: AsyncClient, admin_auth_headers, seeded_service) -> None:
    r = await client.patch(
        f"/api/v1/admin/fees/services/{seeded_service.id}",
        headers=admin_auth_headers,
        json={"subscription_enabled": True, "freebie_default_days": 45, "order_value_percent": 2.5},
    )
    assert r.status_code == 200
    assert r.json()["subscription_enabled"] is True
    assert r.json()["freebie_default_days"] == 45
    assert r.json()["order_value_percent"] == 2.5


@pytest.mark.asyncio
async def test_service_config_unknown_service_404(client: AsyncClient, admin_auth_headers) -> None:
    r = await client.get("/api/v1/admin/fees/services/999999", headers=admin_auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_put_plans_replaces_set(client: AsyncClient, admin_auth_headers, seeded_service) -> None:
    r = await client.put(
        f"/api/v1/admin/fees/services/{seeded_service.id}/plans",
        headers=admin_auth_headers,
        json={"plans": [
            {"duration_months": 3, "price": 300, "is_active": True},
            {"duration_months": 6, "price": 500, "is_active": True},
        ]},
    )
    assert r.status_code == 200
    assert {p["duration_months"] for p in r.json()} == {3, 6}
    # Replace: send only the 12-month plan; 3 and 6 must be dropped.
    r2 = await client.put(
        f"/api/v1/admin/fees/services/{seeded_service.id}/plans",
        headers=admin_auth_headers,
        json={"plans": [{"duration_months": 12, "price": 900, "is_active": True}]},
    )
    assert r2.status_code == 200
    assert [p["duration_months"] for p in r2.json()] == [12]


@pytest.mark.asyncio
async def test_put_plans_rejects_bad_duration(client: AsyncClient, admin_auth_headers, seeded_service) -> None:
    r = await client.put(
        f"/api/v1/admin/fees/services/{seeded_service.id}/plans",
        headers=admin_auth_headers,
        json={"plans": [{"duration_months": 4, "price": 100, "is_active": True}]},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_payment_method_flags_default_false_and_roundtrip(
    client: AsyncClient, admin_auth_headers
) -> None:
    # Fresh installs offer no method until the admin explicitly enables one.
    r = await client.get("/api/v1/admin/fees/settings", headers=admin_auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["upi_enabled"] is False
    assert body["bank_transfer_enabled"] is False

    # Enable UPI with a valid id (bank stays off) — flag persists.
    r2 = await client.patch(
        "/api/v1/admin/fees/settings",
        headers=admin_auth_headers,
        json={"upi_enabled": True, "upi_id": "pay@oksbi"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["upi_enabled"] is True
    assert r2.json()["bank_transfer_enabled"] is False


@pytest.mark.asyncio
async def test_enabling_upi_without_details_rejected(
    client: AsyncClient, admin_auth_headers
) -> None:
    # Bank disabled so only the UPI guard can fire; no upi_id and no QR → 400.
    r = await client.patch(
        "/api/v1/admin/fees/settings",
        headers=admin_auth_headers,
        json={
            "upi_enabled": True,
            "bank_transfer_enabled": False,
            "upi_id": "",
            "qr_image_url": "",
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "upi_incomplete"


@pytest.mark.asyncio
async def test_enabling_bank_without_details_rejected(
    client: AsyncClient, admin_auth_headers
) -> None:
    # UPI disabled so only the bank guard can fire; IFSC missing → 400.
    r = await client.patch(
        "/api/v1/admin/fees/settings",
        headers=admin_auth_headers,
        json={
            "upi_enabled": False,
            "bank_transfer_enabled": True,
            "bank_account_number": "123",
            "bank_ifsc": "",
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "bank_incomplete"
