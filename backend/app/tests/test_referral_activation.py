# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlmodel import select

from app.models.base import User, UserRole
from app.models.notification import Notification, NotificationType
from app.models.profile import CustomerProfile
from app.models.referral import Referral, ReferralStatus, ReferralTargetRole
from app.services import referrals as svc


def _approved_referral(**over) -> Referral:
    base = dict(
        source_user_id=1,
        source_role=UserRole.Customer,
        target_role=ReferralTargetRole.customer,
        invitee_name="Asha",
        invitee_email="asha@example.com",
        location_state="Maharashtra",
        location_area="Pune",
        status=ReferralStatus.approved,
    )
    base.update(over)
    return Referral(**base)


@pytest.mark.asyncio
async def test_issue_invite_sets_expiry_and_token(session):
    r = _approved_referral()
    session.add(r)
    await session.flush()
    token = await svc.issue_invite_and_dispatch(session, referral=r)
    await session.commit()
    await session.refresh(r)
    assert r.invite_expires_at is not None
    assert isinstance(token, str) and token


@pytest.mark.asyncio
async def test_record_referrer_notification_customer(session):
    user = User(email="ref@x.test", role=UserRole.Customer)
    session.add(user)
    await session.flush()
    prof = CustomerProfile(user_id=user.id, first_name="Ref")
    session.add(prof)
    await session.flush()
    r = _approved_referral(source_user_id=user.id)
    session.add(r)
    await session.flush()
    await svc.record_referral_notification(session, referral=r, event="approved")
    await session.commit()
    notif = (
        await session.exec(
            select(Notification).where(Notification.customer_profile_id == prof.id)
        )
    ).first()
    assert notif is not None
    assert notif.type == NotificationType.Referral
    assert notif.status_value == "approved"


# ─── Customer activation (invite detail + accept) ────────────────────────
from datetime import datetime, timedelta, timezone  # noqa: E402

from app.core.security import create_referral_invite_token  # noqa: E402


async def _noop_verify(*a, **kw):
    return True


@pytest.mark.asyncio
async def test_invite_detail(client, session):
    r = _approved_referral(invitee_email="detail@example.com")
    r.invite_expires_at = datetime.now(timezone.utc) + timedelta(days=14)
    session.add(r)
    await session.commit()
    await session.refresh(r)
    tok = create_referral_invite_token(
        referral_id=r.id, target_role="customer", email="detail@example.com",
        phone=None, expires_days=14,
    )
    res = await client.get(f"/api/v1/referrals/invite?token={tok}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["invitee_name"] == "Asha"
    assert body["target_role"] == "customer"
    assert body["expired"] is False


@pytest.mark.asyncio
async def test_accept_creates_customer(client, session, monkeypatch):
    r = _approved_referral(invitee_email="join@example.com")
    r.invite_expires_at = datetime.now(timezone.utc) + timedelta(days=14)
    session.add(r)
    await session.commit()
    await session.refresh(r)
    rid = r.id
    tok = create_referral_invite_token(
        referral_id=rid, target_role="customer", email="join@example.com",
        phone=None, expires_days=14,
    )
    monkeypatch.setattr("app.api.referrals.verify_otp", _noop_verify)
    monkeypatch.setattr("app.api.referrals.consume_otp_key", _noop_verify)
    res = await client.post(
        "/api/v1/referrals/accept",
        json={"token": tok, "code": "123456", "full_name": "Asha Rao", "accept_policies": True},
    )
    assert res.status_code == 200, res.text
    assert res.json()["access_token"]
    fresh = await session.get(Referral, rid)
    await session.refresh(fresh)
    assert fresh.status == ReferralStatus.active
    assert fresh.activated_user_id is not None


@pytest.mark.asyncio
async def test_accept_expired_invite_conflict(client, session, monkeypatch):
    r = _approved_referral(invitee_email="stale@example.com")
    r.invite_expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    session.add(r)
    await session.commit()
    await session.refresh(r)
    tok = create_referral_invite_token(
        referral_id=r.id, target_role="customer", email="stale@example.com",
        phone=None, expires_days=14,
    )
    monkeypatch.setattr("app.api.referrals.verify_otp", _noop_verify)
    monkeypatch.setattr("app.api.referrals.consume_otp_key", _noop_verify)
    res = await client.post(
        "/api/v1/referrals/accept",
        json={"token": tok, "code": "123456", "accept_policies": True},
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "expired"
