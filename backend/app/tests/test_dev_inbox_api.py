# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings


async def _seed_emails(session: AsyncSession, n: int) -> None:
    from app.models.dev_email import DevEmail

    for i in range(n):
        session.add(
            DevEmail(
                to_email=f"user{i}@shop.com",
                subject=f"Order {i}",
                body_text=f"body {i}",
                body_html=None,
                reply_to=None,
                category=None,
                provider="console",
            )
        )
    await session.commit()


@pytest.fixture
def _dev_inbox_creds(monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "DEV_INBOX_USER", "devuser")
    monkeypatch.setattr(settings, "DEV_INBOX_PASSWORD", "secret")
    return ("devuser", "secret")


@pytest.mark.asyncio
async def test_list_emails_requires_auth(
    client: AsyncClient, _dev_inbox_creds: tuple[str, str]
) -> None:
    resp = await client.get("/api/v1/dev/emails")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_emails_rejects_bad_creds(
    client: AsyncClient, _dev_inbox_creds: tuple[str, str]
) -> None:
    resp = await client.get("/api/v1/dev/emails", auth=("devuser", "wrong"))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_emails_paginates_newest_first(
    client: AsyncClient, session: AsyncSession, _dev_inbox_creds: tuple[str, str]
) -> None:
    await _seed_emails(session, 25)
    resp = await client.get("/api/v1/dev/emails?limit=20&offset=0", auth=_dev_inbox_creds)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 25
    assert len(data["items"]) == 20
    # newest first => highest id first => "Order 24"
    assert data["items"][0]["subject"] == "Order 24"


@pytest.mark.asyncio
async def test_search_filters_emails(
    client: AsyncClient, session: AsyncSession, _dev_inbox_creds: tuple[str, str]
) -> None:
    await _seed_emails(session, 25)
    resp = await client.get("/api/v1/dev/emails?q=user1@shop.com", auth=_dev_inbox_creds)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(it["to_email"] == "user1@shop.com" for it in items)
    assert len(items) == 1


@pytest.mark.asyncio
async def test_emails_new_count(
    client: AsyncClient, session: AsyncSession, _dev_inbox_creds: tuple[str, str]
) -> None:
    await _seed_emails(session, 5)
    listing = (await client.get("/api/v1/dev/emails", auth=_dev_inbox_creds)).json()
    latest_id = listing["items"][0]["id"]
    await _seed_emails(session, 3)
    resp = await client.get(
        f"/api/v1/dev/emails/new-count?after={latest_id}", auth=_dev_inbox_creds
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 3


@pytest.mark.asyncio
async def test_endpoints_404_outside_development(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "DEV_INBOX_USER", "devuser")
    monkeypatch.setattr(settings, "DEV_INBOX_PASSWORD", "secret")
    resp = await client.get("/api/v1/dev/emails", auth=("devuser", "secret"))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sms_listing(
    client: AsyncClient, session: AsyncSession, _dev_inbox_creds: tuple[str, str]
) -> None:
    from app.models.dev_sms import DevSms

    session.add(DevSms(to_phone="+919800000001", body="otp 1111", provider="console"))
    session.add(DevSms(to_phone="+919800000002", body="otp 2222", provider="console"))
    await session.commit()
    resp = await client.get("/api/v1/dev/sms", auth=_dev_inbox_creds)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["items"][0]["body"] == "otp 2222"  # newest first


@pytest.mark.asyncio
async def test_list_whatsapp_requires_auth(
    client: AsyncClient, _dev_inbox_creds: tuple[str, str]
) -> None:
    resp = await client.get("/api/v1/dev/whatsapp")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_whatsapp_listing_and_search(
    client: AsyncClient, session: AsyncSession, _dev_inbox_creds: tuple[str, str]
) -> None:
    from app.models.dev_whatsapp import DevWhatsApp

    session.add(
        DevWhatsApp(
            to_phone="+919800000001", body="login code 1111",
            template="otp_login", category="AUTHENTICATION", provider="console",
        )
    )
    session.add(
        DevWhatsApp(
            to_phone="+919800000002", body="order #5 dispatched",
            template="order_dispatched", category="UTILITY", provider="console",
        )
    )
    await session.commit()

    resp = await client.get("/api/v1/dev/whatsapp", auth=_dev_inbox_creds)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["items"][0]["template"] == "order_dispatched"  # newest first

    # Search matches the template column too.
    resp = await client.get("/api/v1/dev/whatsapp?q=otp_login", auth=_dev_inbox_creds)
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["to_phone"] == "+919800000001"


@pytest.mark.asyncio
async def test_whatsapp_new_count(
    client: AsyncClient, session: AsyncSession, _dev_inbox_creds: tuple[str, str]
) -> None:
    from app.models.dev_whatsapp import DevWhatsApp

    session.add(DevWhatsApp(to_phone="+919800000001", body="a", provider="console"))
    await session.commit()
    listing = (await client.get("/api/v1/dev/whatsapp", auth=_dev_inbox_creds)).json()
    latest_id = listing["items"][0]["id"]
    session.add(DevWhatsApp(to_phone="+919800000002", body="b", provider="console"))
    session.add(DevWhatsApp(to_phone="+919800000003", body="c", provider="console"))
    await session.commit()
    resp = await client.get(
        f"/api/v1/dev/whatsapp/new-count?after={latest_id}", auth=_dev_inbox_creds
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 2
