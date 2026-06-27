# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import re

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.email import get_email_sender
from app.core.security import create_seller_signup_token
from app.models.base import User, UserRole
from app.models.catalog import Service, ServiceTranslation
from app.models.consent import PolicyAcceptance, PolicyDocument, PolicyKind
from app.services import consent as consent_svc
from tests._helpers import make_address


class _FakeEmailSender:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(
        self, to, subject, *, text, html=None, reply_to=None
    ) -> None:  # type: ignore[no-untyped-def]
        self.sent.append({"to": to, "subject": subject, "text": text})


def _extract_code(text: str) -> str:
    match = re.search(r"\b(\d{6})\b", text)
    assert match, f"no 6-digit code in {text!r}"
    return match.group(1)


async def _publish_both(session: AsyncSession) -> None:
    session.add(PolicyDocument(kind=PolicyKind.terms, version=1, body="t"))
    session.add(PolicyDocument(kind=PolicyKind.privacy, version=1, body="p"))
    await session.commit()


@pytest.fixture
def otp_client():  # type: ignore[no-untyped-def]
    sender = _FakeEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    yield sender
    app.dependency_overrides.pop(get_email_sender, None)


@pytest.mark.asyncio
async def test_policy_document_unique_kind_version(session: AsyncSession) -> None:
    session.add(PolicyDocument(kind=PolicyKind.terms, version=1, body="v1", published_by=None))
    await session.commit()
    session.add(PolicyDocument(kind=PolicyKind.terms, version=1, body="dup", published_by=None))
    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.asyncio
async def test_policy_acceptance_unique_user_version(session: AsyncSession) -> None:
    user = User(email="c1@kb.test", role=UserRole.Customer)
    session.add(user)
    await session.flush()
    assert user.id is not None
    session.add(PolicyAcceptance(user_id=user.id, policy_version="t1-p1"))
    await session.commit()
    session.add(PolicyAcceptance(user_id=user.id, policy_version="t1-p1"))
    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.asyncio
async def test_effective_version_none_until_both_published(session: AsyncSession) -> None:
    assert await consent_svc.get_effective_policy_version(session) is None
    session.add(PolicyDocument(kind=PolicyKind.terms, version=1, body="t"))
    await session.commit()
    # Only terms published → still dormant.
    assert await consent_svc.get_effective_policy_version(session) is None
    session.add(PolicyDocument(kind=PolicyKind.privacy, version=1, body="p"))
    await session.commit()
    assert await consent_svc.get_effective_policy_version(session) == "t1-p1"


@pytest.mark.asyncio
async def test_record_and_has_accepted(session: AsyncSession) -> None:
    session.add(PolicyDocument(kind=PolicyKind.terms, version=1, body="t"))
    session.add(PolicyDocument(kind=PolicyKind.privacy, version=1, body="p"))
    user = User(email="acc@kb.test", role=UserRole.Customer)
    session.add(user)
    await session.commit()
    assert user.id is not None

    assert await consent_svc.has_accepted_current_policy(session, user.id) is False
    version = await consent_svc.record_acceptance(session, user.id)
    await session.commit()
    assert version == "t1-p1"
    assert await consent_svc.has_accepted_current_policy(session, user.id) is True
    # Idempotent: second call inserts nothing and does not raise.
    assert await consent_svc.record_acceptance(session, user.id) == "t1-p1"
    await session.commit()


@pytest.mark.asyncio
async def test_version_bump_unsets_acceptance(session: AsyncSession) -> None:
    session.add(PolicyDocument(kind=PolicyKind.terms, version=1, body="t"))
    session.add(PolicyDocument(kind=PolicyKind.privacy, version=1, body="p"))
    user = User(email="bump@kb.test", role=UserRole.Customer)
    session.add(user)
    await session.commit()
    assert user.id is not None
    await consent_svc.record_acceptance(session, user.id)
    await session.commit()
    assert await consent_svc.has_accepted_current_policy(session, user.id) is True
    # Publish terms v2 → effective version changes → acceptance is stale.
    session.add(PolicyDocument(kind=PolicyKind.terms, version=2, body="t2"))
    await session.commit()
    assert await consent_svc.get_effective_policy_version(session) == "t2-p1"
    assert await consent_svc.has_accepted_current_policy(session, user.id) is False


@pytest.mark.asyncio
async def test_public_policy_get_404_then_content(session: AsyncSession) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/v1/policies/terms")
        assert r.status_code == 404
        # Publish two versions; GET returns the latest.
        session.add(PolicyDocument(kind=PolicyKind.terms, version=1, body="old"))
        session.add(PolicyDocument(kind=PolicyKind.terms, version=2, body="new terms"))
        await session.commit()
        r = await ac.get("/api/v1/policies/terms")
        assert r.status_code == 200
        data = r.json()
        assert data["version"] == 2
        assert data["body"] == "new terms"
        assert data["kind"] == "terms"


@pytest.mark.asyncio
async def test_public_policy_status(session: AsyncSession) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/v1/policies/status")
        assert r.status_code == 200
        assert r.json() == {"required": False, "version": None}
        session.add(PolicyDocument(kind=PolicyKind.terms, version=1, body="t"))
        session.add(PolicyDocument(kind=PolicyKind.privacy, version=1, body="p"))
        await session.commit()
        r = await ac.get("/api/v1/policies/status")
        assert r.json() == {"required": True, "version": "t1-p1"}


@pytest.mark.asyncio
async def test_public_policy_get_rejects_unknown_kind(session: AsyncSession) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/v1/policies/marketing")
        assert r.status_code == 422


@pytest.fixture
def override_admin():  # type: ignore[no-untyped-def]
    from app.core.security import get_current_admin, get_current_user
    admin = User(id=90100, email="admin-p@kb.test", role=UserRole.Admin, is_active=True)
    app.dependency_overrides[get_current_admin] = lambda: admin
    app.dependency_overrides[get_current_user] = lambda: admin
    yield admin
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_publish_increments_version(override_admin, session: AsyncSession) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/api/v1/admin/policies/terms", json={"body": "first"})
        assert r.status_code == 200, r.text
        assert r.json()["version"] == 1
        r = await ac.post("/api/v1/admin/policies/terms", json={"body": "second"})
        assert r.json()["version"] == 2
        # Public GET reflects the latest.
        pub = await ac.get("/api/v1/policies/terms")
        assert pub.json()["version"] == 2 and pub.json()["body"] == "second"
        # History lists both, newest first.
        hist = await ac.get("/api/v1/admin/policies/terms/history")
        versions = [row["version"] for row in hist.json()]
        assert versions == [2, 1]


@pytest.mark.asyncio
async def test_admin_publish_requires_admin(customer_auth_headers) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/api/v1/admin/policies/terms", json={"body": "x"})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_list_policies(override_admin, session: AsyncSession) -> None:
    session.add(PolicyDocument(kind=PolicyKind.privacy, version=1, body="p1"))
    await session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/v1/admin/policies")
        assert r.status_code == 200
        by_kind = {row["kind"]: row for row in r.json()}
        assert by_kind["privacy"]["version"] == 1 and by_kind["privacy"]["body"] == "p1"
        # Unpublished kind appears with version 0 / empty body.
        assert by_kind["terms"]["version"] == 0


@pytest.mark.asyncio
async def test_customer_signup_requires_accept_when_active(otp_client, session: AsyncSession) -> None:
    await _publish_both(session)
    sender = otp_client
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/api/v1/auth/otp/request", json={"email": "newcust@example.com"})
        code = _extract_code(sender.sent[-1]["text"])
        r = await c.post(
            "/api/v1/auth/otp/verify",
            json={"email": "newcust@example.com", "code": code, "full_name": "New Cust"},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "policy_acceptance_required"
    res = await session.exec(select(User).where(User.email == "newcust@example.com"))
    assert res.first() is None


@pytest.mark.asyncio
async def test_customer_signup_records_acceptance(otp_client, session: AsyncSession) -> None:
    await _publish_both(session)
    sender = otp_client
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/api/v1/auth/otp/request", json={"email": "ok@example.com"})
        code = _extract_code(sender.sent[-1]["text"])
        r = await c.post(
            "/api/v1/auth/otp/verify",
            json={
                "email": "ok@example.com",
                "code": code,
                "full_name": "Ok User",
                "accept_policies": True,
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["user"]["needs_policy_acceptance"] is False
    res = await session.exec(select(User).where(User.email == "ok@example.com"))
    user = res.first()
    assert user is not None
    acc = await session.exec(
        select(PolicyAcceptance).where(PolicyAcceptance.user_id == user.id)
    )
    rows = acc.all()
    assert len(rows) == 1 and rows[0].policy_version == "t1-p1"


@pytest.mark.asyncio
async def test_seller_register_requires_accept_when_active(session: AsyncSession) -> None:
    await _publish_both(session)
    svc = Service(slug="grocery", is_active=True, sort_order=0)
    session.add(svc)
    await session.flush()
    assert svc.id is not None
    session.add(ServiceTranslation(service_id=svc.id, language_code="en", name="Grocery"))
    await session.commit()
    token = create_seller_signup_token("sellerx@test.com", "+919876543210")
    payload = {
        "signup_token": token,
        "full_name": "Priya Verma",
        "business_name": "Priya Grocery",
        "service_ids": [svc.id],
        "address": make_address(),
        "gst_number": "29ABCDE1234F1Z5",
        "fssai_license": "10020042000015",
        "bank_account_number": "123456789012",
        "bank_ifsc": "SBIN0001234",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/api/v1/auth/seller/register", json=payload)
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "policy_acceptance_required"


@pytest.mark.asyncio
async def test_accept_endpoint_idempotent(override_admin, session: AsyncSession) -> None:
    await _publish_both(session)
    session.add(User(id=90100, email="admin-p@kb.test", role=UserRole.Admin))
    await session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/api/v1/auth/policy/accept")
        assert r.status_code == 200
        assert r.json() == {"accepted": True, "version": "t1-p1"}
        r2 = await ac.post("/api/v1/auth/policy/accept")
        assert r2.status_code == 200
    acc = await session.exec(
        select(PolicyAcceptance).where(PolicyAcceptance.user_id == 90100)
    )
    assert len(acc.all()) == 1


@pytest.mark.asyncio
async def test_me_reports_needs_then_clears(override_admin, session: AsyncSession) -> None:
    await _publish_both(session)
    session.add(User(id=90100, email="admin-p@kb.test", role=UserRole.Admin))
    await session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        me = await ac.get("/api/v1/auth/me")
        assert me.json()["needs_policy_acceptance"] is True
        await ac.post("/api/v1/auth/policy/accept")
        me2 = await ac.get("/api/v1/auth/me")
        assert me2.json()["needs_policy_acceptance"] is False
