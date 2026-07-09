# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest

from app.models.base import User, UserRole
from app.models.referral import ReferralStatus, ReferralTargetRole
from app.schemas.referrals import ReferralCreate
from app.services import referrals as svc


def _payload(**over):
    base = dict(
        target_role=ReferralTargetRole.customer,
        invitee_name="Asha",
        invitee_email="asha@example.com",
        location_state="Maharashtra",
        location_area="Pune",
    )
    base.update(over)
    return ReferralCreate(**base)


@pytest.mark.asyncio
async def test_create_referral_pending_by_default(session):
    r = await svc.create_referral(
        session, source_user_id=7, source_role=UserRole.Customer, payload=_payload()
    )
    await session.commit()
    assert r.status == ReferralStatus.pending_review
    assert r.source_user_id == 7


@pytest.mark.asyncio
async def test_duplicate_existing_user_blocks(session):
    session.add(User(email="asha@example.com", role=UserRole.Customer))
    await session.commit()
    with pytest.raises(svc.DuplicateContact) as ei:
        await svc.assert_contact_available(session, email="asha@example.com", phone=None)
    assert ei.value.reason == "already_registered"


@pytest.mark.asyncio
async def test_duplicate_open_referral_blocks(session):
    await svc.create_referral(
        session, source_user_id=7, source_role=UserRole.Customer, payload=_payload()
    )
    await session.commit()
    with pytest.raises(svc.DuplicateContact) as ei:
        await svc.assert_contact_available(session, email="asha@example.com", phone=None)
    assert ei.value.reason == "already_invited"


@pytest.mark.asyncio
async def test_auto_approve_when_setting_disabled(session):
    settings_row = await svc.get_or_create_referral_settings(session)
    settings_row.require_admin_approval = False
    session.add(settings_row)
    await session.commit()
    r = await svc.create_referral(
        session, source_user_id=7, source_role=UserRole.Customer,
        payload=_payload(invitee_email="auto@example.com"),
    )
    await session.commit()
    assert r.status == ReferralStatus.approved


# ─── Endpoint tests ──────────────────────────────────────────────────────
VALID = {
    "target_role": "customer",
    "invitee_name": "Asha Rao",
    "invitee_email": "asha@example.com",
    "location_state": "Maharashtra",
    "location_area": "Kothrud, Pune",
}


@pytest.mark.asyncio
async def test_submit_requires_auth(client):
    r = await client.post("/api/v1/referrals", json=VALID)
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_submit_and_list(client, customer_auth_headers):
    r = await client.post("/api/v1/referrals", json=VALID, headers=customer_auth_headers)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pending_review"
    lst = await client.get("/api/v1/referrals", headers=customer_auth_headers)
    assert lst.status_code == 200
    assert any(x["invitee_email"] == "asha@example.com" for x in lst.json()["items"])


@pytest.mark.asyncio
async def test_submit_missing_contact_422(client, customer_auth_headers):
    bad = {**VALID}
    del bad["invitee_email"]
    r = await client.post("/api/v1/referrals", json=bad, headers=customer_auth_headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_submit_duplicate_returns_409(client, customer_auth_headers):
    await client.post("/api/v1/referrals", json=VALID, headers=customer_auth_headers)
    r = await client.post("/api/v1/referrals", json=VALID, headers=customer_auth_headers)
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "already_invited"


@pytest.mark.asyncio
async def test_get_other_users_referral_404(client, customer_auth_headers, session):
    from app.models.referral import Referral, ReferralTargetRole

    other = Referral(
        source_user_id=88888,
        source_role=UserRole.Customer,
        target_role=ReferralTargetRole.customer,
        invitee_name="Someone",
        invitee_email="someone@example.com",
        location_state="Maharashtra",
        location_area="Pune",
    )
    session.add(other)
    await session.commit()
    await session.refresh(other)
    r = await client.get(f"/api/v1/referrals/{other.id}", headers=customer_auth_headers)
    assert r.status_code == 404
