# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.mark.asyncio
async def test_dev_email_table_roundtrips(session: AsyncSession) -> None:
    from app.models.dev_email import DevEmail

    session.add(
        DevEmail(
            to_email="a@b.com",
            subject="Hi",
            body_text="body",
            body_html="<p>body</p>",
            reply_to="support@x.com",
            category=None,
            provider="console",
        )
    )
    await session.commit()
    rows = (await session.exec(select(DevEmail))).all()
    assert len(rows) == 1
    assert rows[0].to_email == "a@b.com"
    assert rows[0].id is not None


@pytest.mark.asyncio
async def test_dev_sms_table_roundtrips(session: AsyncSession) -> None:
    from app.models.dev_sms import DevSms

    session.add(DevSms(to_phone="+919812345678", body="code 1234", provider="console"))
    await session.commit()
    rows = (await session.exec(select(DevSms))).all()
    assert len(rows) == 1
    assert rows[0].to_phone == "+919812345678"


@pytest.mark.asyncio
async def test_record_outbound_email_writes_row(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import dev_mailbox
    from app.core.config import settings
    from app.models.dev_email import DevEmail

    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    await dev_mailbox.record_outbound_email(
        to="x@y.com", subject="S", text="T", html="<p>T</p>", reply_to=None
    )
    rows = (await session.exec(select(DevEmail))).all()
    assert len(rows) == 1
    assert rows[0].subject == "S"
    assert rows[0].body_html == "<p>T</p>"


@pytest.mark.asyncio
async def test_record_outbound_email_noop_outside_dev(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import dev_mailbox
    from app.core.config import settings
    from app.models.dev_email import DevEmail

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    await dev_mailbox.record_outbound_email(to="x@y.com", subject="S", text="T")
    rows = (await session.exec(select(DevEmail))).all()
    assert rows == []


@pytest.mark.asyncio
async def test_record_outbound_sms_writes_row(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import dev_mailbox
    from app.core.config import settings
    from app.models.dev_sms import DevSms

    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    await dev_mailbox.record_outbound_sms(to="+919812345678", text="code 1234")
    rows = (await session.exec(select(DevSms))).all()
    assert len(rows) == 1
    assert rows[0].body == "code 1234"


@pytest.mark.asyncio
async def test_console_email_sender_captures(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings
    from app.core.email import ConsoleEmailSender
    from app.models.dev_email import DevEmail

    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    await ConsoleEmailSender().send(
        "u@v.com", "Subject Z", text="hello", html="<b>hello</b>"
    )
    rows = (await session.exec(select(DevEmail))).all()
    assert len(rows) == 1
    assert rows[0].subject == "Subject Z"


@pytest.mark.asyncio
async def test_console_sms_sender_captures(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings
    from app.core.sms import ConsoleSMSSender
    from app.models.dev_sms import DevSms

    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    await ConsoleSMSSender().send("+919800000000", "your code 9999")
    rows = (await session.exec(select(DevSms))).all()
    assert len(rows) == 1
    assert rows[0].body == "your code 9999"


@pytest.mark.asyncio
async def test_worker_resolve_email_captures(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Exercises the sync Celery chokepoint: _resolve_email bridges to the async
    # recorder via ThreadPoolExecutor + asyncio.run. Runs on the console branch.
    from app import worker
    from app.core.config import settings
    from app.models.dev_email import DevEmail

    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "console")
    worker._resolve_email(
        "w@x.com", "Worker Subj", "worker body", html="<i>b</i>", reply_to=None
    )
    rows = (await session.exec(select(DevEmail))).all()
    assert len(rows) == 1
    assert rows[0].subject == "Worker Subj"
    assert rows[0].body_text == "worker body"
