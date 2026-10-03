# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.admin_audit import AdminActionLog
from app.models.profile import VerificationStatus
from tests._courier_helpers import (
    ADMIN,
    CUSTOMER,
    SELLER,
    client_as,
    seed_courier_world,
)

PENDING = VerificationStatus.Pending


def _profile_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "business_name": "Ravi Sweets",
        "address": {
            "address_line1": "12 MG Road", "city": "Bengaluru", "state": "Karnataka",
            "pincode": "560002", "country": "India",
        },
        "phone": "+919900000002",
        "bank_account_number": "123456789012",
        "bank_ifsc": "HDFC0001234",
    }
    body.update(overrides)
    return body


async def test_pending_seller_sets_keeps_and_clears_courier_radius(session: AsyncSession) -> None:
    world = await seed_courier_world(session, courier_radius_km=None, seller_status=PENDING)
    url = f"/api/v1/stores/{world.store_id}"
    async with client_as(SELLER) as ac:
        set_resp = await ac.patch(url, json={"courier_radius_km": 800})
        kept = await ac.patch(url, json={"pin_confirmed": True})
        cleared = await ac.patch(url, json={"courier_radius_km": 0})
    assert set_resp.status_code == 200, set_resp.text
    assert set_resp.json()["courier_radius_km"] == 800
    assert kept.json()["courier_radius_km"] == 800
    assert cleared.json()["courier_radius_km"] is None


async def test_courier_radius_must_exceed_local_and_respect_cap(session: AsyncSession) -> None:
    world = await seed_courier_world(session, courier_radius_km=None, seller_status=PENDING)
    url = f"/api/v1/stores/{world.store_id}"
    async with client_as(SELLER) as ac:
        equal = await ac.patch(url, json={"courier_radius_km": 5})  # local radius is 5
        huge = await ac.patch(url, json={"courier_radius_km": 3501})
        ok = await ac.patch(url, json={"courier_radius_km": 10})
        widened_local = await ac.patch(url, json={"delivery_radius_km": 12})
    assert equal.status_code == 422 and equal.json()["detail"] == "courier_radius_not_larger"
    assert huge.status_code == 422 and huge.json()["detail"] == "courier_radius_too_large"
    assert ok.status_code == 200
    assert widened_local.status_code == 422
    assert widened_local.json()["detail"] == "courier_radius_not_larger"


async def test_approved_seller_must_use_a_change_request(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    async with client_as(SELLER) as ac:
        resp = await ac.patch(f"/api/v1/stores/{world.store_id}", json={"courier_radius_km": 600})
    assert resp.status_code == 409 and resp.json()["detail"] == "use_change_request"


async def test_store_read_exposes_courier_fields(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    async with client_as(CUSTOMER) as ac:
        resp = await ac.get(f"/api/v1/stores/{world.store_id}")
    assert resp.json()["courier_radius_km"] == 500.0
    assert resp.json()["courier_payment_methods"] == ["upi", "net_banking"]
    service = next(s for s in resp.json()["services"] if s["id"] == world.service_id)
    assert service["courier_enabled"] is True


async def test_pending_seller_toggles_courier_per_service(session: AsyncSession) -> None:
    world = await seed_courier_world(session, courier_enabled=False, seller_status=PENDING)
    async with client_as(SELLER) as ac:
        resp = await ac.patch(f"/api/v1/sellers/me/services/{world.service_id}", json={
            "free_delivery_threshold": 500, "delivery_fee": 30, "courier_enabled": True,
        })
        untouched = await ac.patch(f"/api/v1/sellers/me/services/{world.service_id}", json={
            "free_delivery_threshold": 400, "delivery_fee": 30,
        })
    assert resp.status_code == 200, resp.text
    assert resp.json()["courier_enabled"] is True
    assert untouched.json()["courier_enabled"] is True


async def test_admin_toggle_is_audited(session: AsyncSession) -> None:
    world = await seed_courier_world(session, courier_enabled=False)
    async with client_as(ADMIN) as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/admin/{SELLER.id}/services/{world.service_id}",
            json={"free_delivery_threshold": 500, "delivery_fee": 30, "courier_enabled": True},
        )
    assert resp.status_code == 200, resp.text
    log = (
        await session.exec(
            select(AdminActionLog).where(AdminActionLog.action == "service.set_delivery_settings")
        )
    ).one()
    assert log.before_json is not None and log.after_json is not None
    assert log.before_json["courier_enabled"] is False
    assert log.after_json["courier_enabled"] is True


async def test_pending_seller_bank_transfer_needs_complete_details(session: AsyncSession) -> None:
    await seed_courier_world(session, seller_status=PENDING)
    async with client_as(SELLER) as ac:
        missing = await ac.patch("/api/v1/sellers/me/profile", json=_profile_body(
            bank_account_name="", bank_transfer_enabled=True,
        ))
        ok = await ac.patch("/api/v1/sellers/me/profile", json=_profile_body(
            bank_account_name="Ravi Sweets", bank_transfer_enabled=True,
        ))
        profile = await ac.get("/api/v1/sellers/me/profile")
    assert missing.status_code == 422 and missing.json()["detail"] == "bank_transfer_incomplete"
    assert ok.status_code == 200, ok.text
    assert profile.json()["bank_account_name"] == "Ravi Sweets"
    assert profile.json()["bank_transfer_enabled"] is True


async def test_a_lowered_cap_only_binds_a_ring_the_request_sets(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ops lowering COURIER_MAX_RADIUS_KM below a store's existing ring must
    not block unrelated edits; a new ring above the cap is still refused."""
    from app.core.config import settings

    world = await seed_courier_world(session, seller_status=PENDING)  # ring 500 km
    monkeypatch.setattr(settings, "COURIER_MAX_RADIUS_KM", 300.0)
    url = f"/api/v1/stores/{world.store_id}"
    async with client_as(SELLER) as ac:
        pin = await ac.patch(url, json={"pin_confirmed": True})
        local = await ac.patch(url, json={"delivery_radius_km": 8})
        too_big = await ac.patch(url, json={"courier_radius_km": 400})
    assert pin.status_code == 200, pin.text
    assert local.status_code == 200, local.text
    assert local.json()["courier_radius_km"] == 500
    assert too_big.status_code == 422 and too_big.json()["detail"] == "courier_radius_too_large"
