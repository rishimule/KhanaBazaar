# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import User, UserRole
from app.models.notification import Notification, NotificationType
from app.models.profile import CustomerProfile
from app.models.referral import Referral, ReferralStatus, ReferralTargetRole
from app.services import referrals as svc
from tests._helpers import signup_phone_token


def _approved_referral(**over) -> Referral:
    base = {
        "source_user_id": 1,
        "source_role": UserRole.Customer,
        "target_role": ReferralTargetRole.customer,
        "invitee_name": "Asha",
        "invitee_email": "asha@example.com",
        "location_state": "Maharashtra",
        "location_area": "Pune",
        "status": ReferralStatus.approved,
    }
    base.update(over)
    return Referral(**base)


@pytest.mark.asyncio
async def test_issue_invite_sets_expiry_and_token(session):
    r = _approved_referral()
    session.add(r)
    await session.flush()
    token = await svc.issue_invite(session, referral=r)
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
        json={
            "token": tok, "code": "123456", "full_name": "Asha Rao",
            "accept_policies": True,
            "phone_token": signup_phone_token("join@example.com", "+919811100001"),
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["access_token"]
    fresh = await session.get(Referral, rid)
    await session.refresh(fresh)
    assert fresh.status == ReferralStatus.active
    assert fresh.activated_user_id is not None


@pytest.mark.asyncio
async def test_accept_issues_auth_session(client, session, monkeypatch):
    """Referral-accept logs the user in, so it must also open an untrusted
    refresh session and return refresh_token/expires_in alongside the access
    token (see accept_customer_referral in api/referrals.py)."""
    from app.models.auth_session import AuthSession

    r = _approved_referral(invitee_email="sessionjoin@example.com")
    r.invite_expires_at = datetime.now(timezone.utc) + timedelta(days=14)
    session.add(r)
    await session.commit()
    await session.refresh(r)
    tok = create_referral_invite_token(
        referral_id=r.id, target_role="customer", email="sessionjoin@example.com",
        phone=None, expires_days=14,
    )
    monkeypatch.setattr("app.api.referrals.verify_otp", _noop_verify)
    monkeypatch.setattr("app.api.referrals.consume_otp_key", _noop_verify)
    res = await client.post(
        "/api/v1/referrals/accept",
        json={
            "token": tok, "code": "123456", "full_name": "Session Joiner",
            "accept_policies": True,
            "phone_token": signup_phone_token(
                "sessionjoin@example.com", "+919811100002"
            ),
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["refresh_token"]
    assert body["expires_in"] == 15 * 60

    new_user_id = body["user"]["id"]
    row = (
        await session.exec(
            select(AuthSession).where(AuthSession.user_id == new_user_id)
        )
    ).first()
    assert row is not None
    assert row.trusted is False


@pytest.mark.asyncio
async def test_accept_expired_invite_conflict(client, session, monkeypatch):
    # Sends no phone_token on purpose: invite state must be reported before
    # any phone problem (spec §4.5) — don't "fix" this by adding a token.
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


@pytest.mark.asyncio
async def test_accept_verified_number_taken_is_phone_already_in_use(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The proven number is what lands on the profile, so it is what must be
    free (customer scope) — a clean 409, not a 500 from the unique index."""
    owner = User(email="owner@example.com", role=UserRole.Customer)
    session.add(owner)
    await session.flush()
    assert owner.id is not None
    session.add(
        CustomerProfile(user_id=owner.id, first_name="Owner", phone="+919812345678")
    )
    r = _approved_referral(invitee_email="joiner@example.com")
    r.invite_expires_at = datetime.now(timezone.utc) + timedelta(days=14)
    session.add(r)
    await session.commit()
    await session.refresh(r)
    assert r.id is not None
    tok = create_referral_invite_token(
        referral_id=r.id, target_role="customer", email="joiner@example.com",
        phone=None, expires_days=14,
    )
    monkeypatch.setattr("app.api.referrals.verify_otp", _noop_verify)
    monkeypatch.setattr("app.api.referrals.consume_otp_key", _noop_verify)
    res = await client.post(
        "/api/v1/referrals/accept",
        json={
            "token": tok, "code": "123456", "accept_policies": True,
            "phone_token": signup_phone_token("joiner@example.com", "+919812345678"),
        },
    )
    assert res.status_code == 409, res.text
    assert res.json()["detail"]["error"] == "phone_already_in_use"


@pytest.mark.asyncio
async def test_accept_referrer_typed_number_taken_but_invitee_proves_another(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = User(email="owner2@example.com", role=UserRole.Customer)
    session.add(owner)
    await session.flush()
    assert owner.id is not None
    session.add(
        CustomerProfile(user_id=owner.id, first_name="Owner", phone="+919812345670")
    )
    r = _approved_referral(
        invitee_email="switch@example.com", invitee_phone="+919812345670"
    )
    r.invite_expires_at = datetime.now(timezone.utc) + timedelta(days=14)
    session.add(r)
    await session.commit()
    await session.refresh(r)
    assert r.id is not None
    tok = create_referral_invite_token(
        referral_id=r.id, target_role="customer", email="switch@example.com",
        phone="+919812345670", expires_days=14,
    )
    monkeypatch.setattr("app.api.referrals.verify_otp", _noop_verify)
    monkeypatch.setattr("app.api.referrals.consume_otp_key", _noop_verify)
    res = await client.post(
        "/api/v1/referrals/accept",
        json={
            "token": tok, "code": "123456", "accept_policies": True,
            "phone_token": signup_phone_token("switch@example.com", "+919812345671"),
        },
    )
    assert res.status_code == 200, res.text
    profile = (
        await session.exec(
            select(CustomerProfile).where(
                CustomerProfile.user_id == res.json()["user"]["id"]
            )
        )
    ).one()
    assert profile.phone == "+919812345671"
    assert profile.phone_verified_at is not None


@pytest.mark.asyncio
async def test_accept_requires_a_phone_token(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = _approved_referral(invitee_email="nophone@example.com")
    r.invite_expires_at = datetime.now(timezone.utc) + timedelta(days=14)
    session.add(r)
    await session.commit()
    await session.refresh(r)
    rid = r.id
    assert rid is not None
    tok = create_referral_invite_token(
        referral_id=rid, target_role="customer", email="nophone@example.com",
        phone=None, expires_days=14,
    )
    monkeypatch.setattr("app.api.referrals.verify_otp", _noop_verify)
    monkeypatch.setattr("app.api.referrals.consume_otp_key", _noop_verify)
    res = await client.post(
        "/api/v1/referrals/accept",
        json={"token": tok, "code": "123456", "accept_policies": True},
    )
    assert res.status_code == 400
    assert res.json()["detail"]["error"] == "phone_required"
    fresh = await session.get(Referral, rid)
    assert fresh is not None
    await session.refresh(fresh)
    assert fresh.status == ReferralStatus.approved


@pytest.mark.asyncio
async def test_accept_rejects_a_token_for_another_email(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = _approved_referral(invitee_email="mine@example.com")
    r.invite_expires_at = datetime.now(timezone.utc) + timedelta(days=14)
    session.add(r)
    await session.commit()
    await session.refresh(r)
    assert r.id is not None
    tok = create_referral_invite_token(
        referral_id=r.id, target_role="customer", email="mine@example.com",
        phone=None, expires_days=14,
    )
    monkeypatch.setattr("app.api.referrals.verify_otp", _noop_verify)
    monkeypatch.setattr("app.api.referrals.consume_otp_key", _noop_verify)
    res = await client.post(
        "/api/v1/referrals/accept",
        json={
            "token": tok, "code": "123456", "accept_policies": True,
            "phone_token": signup_phone_token("someone-else@example.com"),
        },
    )
    assert res.status_code == 400
    assert res.json()["detail"]["error"] == "invalid_phone_token"


@pytest.mark.asyncio
async def test_accept_phone_only_invite_binds_the_typed_email(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = _approved_referral(invitee_email=None, invitee_phone="+919812300000")
    r.invite_expires_at = datetime.now(timezone.utc) + timedelta(days=14)
    session.add(r)
    await session.commit()
    await session.refresh(r)
    assert r.id is not None
    tok = create_referral_invite_token(
        referral_id=r.id, target_role="customer", email=None,
        phone="+919812300000", expires_days=14,
    )
    monkeypatch.setattr("app.api.referrals.verify_otp", _noop_verify)
    monkeypatch.setattr("app.api.referrals.consume_otp_key", _noop_verify)
    res = await client.post(
        "/api/v1/referrals/accept",
        json={
            "token": tok, "code": "123456", "email": "Typed@Example.com",
            "accept_policies": True,
            "phone_token": signup_phone_token("typed@example.com", "+919812300000"),
        },
    )
    assert res.status_code == 200, res.text


@pytest.mark.asyncio
async def test_accept_phone_unique_race_is_named(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _never_taken(_session: AsyncSession, _phone: str) -> bool:
        return False

    owner = User(email="owner3@example.com", role=UserRole.Customer)
    session.add(owner)
    await session.flush()
    assert owner.id is not None
    session.add(
        CustomerProfile(user_id=owner.id, first_name="Owner", phone="+919812345672")
    )
    r = _approved_referral(invitee_email="racer@example.com")
    r.invite_expires_at = datetime.now(timezone.utc) + timedelta(days=14)
    session.add(r)
    await session.commit()
    await session.refresh(r)
    assert r.id is not None
    tok = create_referral_invite_token(
        referral_id=r.id, target_role="customer", email="racer@example.com",
        phone=None, expires_days=14,
    )
    monkeypatch.setattr("app.services.referrals.customer_phone_taken", _never_taken)
    monkeypatch.setattr("app.api.referrals.verify_otp", _noop_verify)
    monkeypatch.setattr("app.api.referrals.consume_otp_key", _noop_verify)
    res = await client.post(
        "/api/v1/referrals/accept",
        json={
            "token": tok, "code": "123456", "accept_policies": True,
            "phone_token": signup_phone_token("racer@example.com", "+919812345672"),
        },
    )
    assert res.status_code == 409, res.text
    assert res.json()["detail"]["error"] == "phone_already_in_use"


@pytest.mark.asyncio
async def test_accept_registered_email_is_reported_before_the_phone(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    session.add(User(email="taken@example.com", role=UserRole.Customer))
    r = _approved_referral(invitee_email="taken@example.com")
    r.invite_expires_at = datetime.now(timezone.utc) + timedelta(days=14)
    session.add(r)
    await session.commit()
    await session.refresh(r)
    assert r.id is not None
    tok = create_referral_invite_token(
        referral_id=r.id, target_role="customer", email="taken@example.com",
        phone=None, expires_days=14,
    )
    monkeypatch.setattr("app.api.referrals.verify_otp", _noop_verify)
    monkeypatch.setattr("app.api.referrals.consume_otp_key", _noop_verify)
    res = await client.post(
        "/api/v1/referrals/accept",
        json={"token": tok, "code": "123456", "accept_policies": True},
    )
    assert res.status_code == 409, res.text
    assert res.json()["detail"]["error"] == "already_registered"


@pytest.mark.asyncio
async def test_accept_email_unique_race_is_named(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another tab registers the invite email between the pre-check and the
    insert: a clean 409 already_registered, not a 500."""

    async def _other_tab_wins(_s: AsyncSession, _phone: str) -> bool:
        session.add(User(email="racer2@example.com", role=UserRole.Customer))
        await session.commit()
        return False

    r = _approved_referral(invitee_email="racer2@example.com")
    r.invite_expires_at = datetime.now(timezone.utc) + timedelta(days=14)
    session.add(r)
    await session.commit()
    await session.refresh(r)
    assert r.id is not None
    tok = create_referral_invite_token(
        referral_id=r.id, target_role="customer", email="racer2@example.com",
        phone=None, expires_days=14,
    )
    monkeypatch.setattr("app.services.referrals.customer_phone_taken", _other_tab_wins)
    monkeypatch.setattr("app.api.referrals.verify_otp", _noop_verify)
    monkeypatch.setattr("app.api.referrals.consume_otp_key", _noop_verify)
    res = await client.post(
        "/api/v1/referrals/accept",
        json={
            "token": tok, "code": "123456", "accept_policies": True,
            "phone_token": signup_phone_token("racer2@example.com", "+919812345673"),
        },
    )
    assert res.status_code == 409, res.text
    assert res.json()["detail"]["error"] == "already_registered"


# ─── Seller activation binding ───────────────────────────────────────────
@pytest.mark.asyncio
async def test_seller_register_binds_referral(client, session):
    from app.core.security import create_seller_signup_token
    from app.models.catalog import Service, ServiceTranslation
    from app.models.referral import ReferralTargetRole
    from tests._helpers import make_address

    email = "newseller@example.com"
    phone = "+919812345699"
    r = _approved_referral(
        source_role=UserRole.Seller,
        target_role=ReferralTargetRole.seller,
        invitee_name="New Seller",
        invitee_email=email,
    )
    r.invite_expires_at = datetime.now(timezone.utc) + timedelta(days=14)
    session.add(r)
    svc_row = Service(slug="grocery-ref", is_active=True, sort_order=0)
    session.add(svc_row)
    await session.flush()
    session.add(ServiceTranslation(service_id=svc_row.id, language_code="en", name="Grocery"))
    await session.commit()
    await session.refresh(r)
    rid = r.id
    svc_id = svc_row.id

    invite = create_referral_invite_token(
        referral_id=rid, target_role="seller", email=email, phone=phone, expires_days=14
    )
    signup = create_seller_signup_token(email, phone)
    body = {
        "signup_token": signup,
        "full_name": "New Seller",
        "business_name": "New Store",
        "service_ids": [svc_id],
        "address": make_address(),
        "referral_invite_token": invite,
    }
    res = await client.post("/api/v1/auth/seller/register", json=body)
    assert res.status_code == 200, res.text
    fresh = await session.get(Referral, rid)
    await session.refresh(fresh)
    assert fresh.status == ReferralStatus.active
    assert fresh.activated_user_id is not None
