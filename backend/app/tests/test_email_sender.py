# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosmtplib
import httpx
import pytest
import respx

from app.core.config import settings
from app.core.email import (
    ConsoleEmailSender,
    ResendEmailSender,
)


def test_console_sender_accepts_html_and_text_kwargs():
    sender = ConsoleEmailSender()
    asyncio.run(
        sender.send(
            to="x@example.com",
            subject="hello",
            text="hi",
            html="<p>hi</p>",
            reply_to="rep@example.com",
        )
    )


def test_console_sender_writes_dev_preview_file_when_html_present(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.email._DEV_PREVIEW_DIR", str(tmp_path))
    sender = ConsoleEmailSender()
    asyncio.run(
        sender.send(
            to="x@example.com",
            subject="Preview Test Email",
            text="hi",
            html="<p>hi</p>",
        )
    )
    files = list(Path(tmp_path).glob("khanabazaar_email_*.html"))
    assert len(files) == 1
    assert "<p>hi</p>" in files[0].read_text()


def test_console_sender_skips_preview_when_html_none(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.email._DEV_PREVIEW_DIR", str(tmp_path))
    sender = ConsoleEmailSender()
    asyncio.run(sender.send(to="x@example.com", subject="text only", text="hi"))
    assert list(Path(tmp_path).glob("*.html")) == []


@respx.mock
def test_resend_sender_posts_html_text_and_reply_to():
    route = respx.post("https://api.resend.com/emails").mock(
        return_value=httpx.Response(200, json={"id": "fake"})
    )
    sender = ResendEmailSender()
    asyncio.run(
        sender.send(
            to="x@example.com",
            subject="hello",
            text="hi",
            html="<p>hi</p>",
            reply_to="rep@example.com",
        )
    )
    assert route.called
    payload = route.calls.last.request.content
    assert b'"html": "<p>hi</p>"' in payload
    assert b'"text": "hi"' in payload
    assert b'"reply_to": "rep@example.com"' in payload


def _set_smtp(monkeypatch, *, port=587, use_tls=False):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(settings, "SMTP_PORT", port)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "me@gmail.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "app-pw-1234")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "me@gmail.com")
    monkeypatch.setattr(settings, "SMTP_USE_TLS", use_tls)
    monkeypatch.setattr(settings, "SMTP_TIMEOUT", 10.0)
    monkeypatch.setattr(settings, "EMAIL_BRAND_NAME", "Sarvaka")


def test_smtp_sender_builds_multipart_and_starttls(monkeypatch):
    from app.core.email import SmtpEmailSender

    _set_smtp(monkeypatch, port=587, use_tls=False)
    with patch("app.core.email.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        asyncio.run(
            SmtpEmailSender().send(
                to="x@example.com",
                subject="hello",
                text="hi",
                html="<p>hi</p>",
                reply_to="rep@example.com",
            )
        )
    assert mock_send.await_count == 1
    msg = mock_send.await_args.args[0]
    assert msg["From"] == "Sarvaka <me@gmail.com>"
    assert msg["To"] == "x@example.com"
    assert msg["Subject"] == "hello"
    assert msg["Reply-To"] == "rep@example.com"
    assert msg.get_content_type() == "multipart/alternative"
    kwargs = mock_send.await_args.kwargs
    assert kwargs["hostname"] == "smtp.gmail.com"
    assert kwargs["port"] == 587
    assert kwargs["username"] == "me@gmail.com"
    assert kwargs["password"] == "app-pw-1234"
    assert kwargs["start_tls"] is True
    assert kwargs["use_tls"] is False
    assert kwargs["timeout"] == 10.0


def test_smtp_sender_text_only_and_implicit_ssl(monkeypatch):
    from app.core.email import SmtpEmailSender

    _set_smtp(monkeypatch, port=465, use_tls=True)
    with patch("app.core.email.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        asyncio.run(
            SmtpEmailSender().send(to="x@example.com", subject="s", text="body only")
        )
    msg = mock_send.await_args.args[0]
    assert msg.get_content_type() == "text/plain"
    assert "Reply-To" not in msg
    kwargs = mock_send.await_args.kwargs
    assert kwargs["port"] == 465
    assert kwargs["start_tls"] is False
    assert kwargs["use_tls"] is True


def test_smtp_console_records_provider_smtp_even_when_send_raises(monkeypatch):
    from app.core import dev_mailbox
    from app.core.email import SmtpWithConsoleSender

    recorded: list[dict] = []

    async def fake_record(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(dev_mailbox, "record_outbound_email", fake_record)

    with patch(
        "app.core.email.aiosmtplib.send",
        side_effect=aiosmtplib.SMTPException("gmail said no"),
    ):
        asyncio.run(
            SmtpWithConsoleSender().send(to="x@example.com", subject="s", text="t")
        )

    assert len(recorded) == 1
    assert recorded[0]["provider"] == "smtp"


def test_smtp_console_records_and_sends_on_success(monkeypatch):
    from app.core import dev_mailbox
    from app.core.email import SmtpWithConsoleSender

    _set_smtp(monkeypatch)
    recorded: list[dict] = []

    async def fake_record(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(dev_mailbox, "record_outbound_email", fake_record)
    with patch("app.core.email.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        asyncio.run(
            SmtpWithConsoleSender().send(to="x@example.com", subject="s", text="t")
        )
    # Happy path: the dev-mailbox row is recorded AND the real send is invoked.
    assert mock_send.await_count == 1
    assert len(recorded) == 1
    assert recorded[0]["provider"] == "smtp"


def test_smtp_console_propagates_unexpected_error_after_recording(monkeypatch):
    from app.core import dev_mailbox
    from app.core.email import SmtpWithConsoleSender

    _set_smtp(monkeypatch)
    recorded: list[dict] = []

    async def fake_record(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(dev_mailbox, "record_outbound_email", fake_record)
    # An error type outside the caught set must propagate — the composite only
    # swallows (aiosmtplib.SMTPException, OSError). The console row is written
    # first, so it survives even when the send raises.
    with patch("app.core.email.aiosmtplib.send", side_effect=ValueError("boom")):
        with pytest.raises(ValueError):
            asyncio.run(
                SmtpWithConsoleSender().send(to="x@example.com", subject="s", text="t")
            )
    assert len(recorded) == 1
    assert recorded[0]["provider"] == "smtp"


def test_smtp_console_swallows_oserror_ssl_failure(monkeypatch):
    from app.core import dev_mailbox
    from app.core.email import SmtpWithConsoleSender

    _set_smtp(monkeypatch)
    recorded: list[dict] = []

    async def fake_record(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(dev_mailbox, "record_outbound_email", fake_record)
    # ssl.SSLError is an OSError but NOT an aiosmtplib.SMTPException; the STARTTLS
    # path can raise it raw. The composite must swallow it (broadened catch).
    import ssl

    with patch("app.core.email.aiosmtplib.send", side_effect=ssl.SSLError("bad cert")):
        asyncio.run(
            SmtpWithConsoleSender().send(to="x@example.com", subject="s", text="t")
        )
    assert recorded[0]["provider"] == "smtp"


def test_smtp_sender_warns_when_unconfigured(monkeypatch, caplog):
    from app.core.email import SmtpEmailSender

    monkeypatch.setattr(settings, "SMTP_HOST", "")
    monkeypatch.setattr(settings, "SMTP_USERNAME", "")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")
    with caplog.at_level(logging.WARNING, logger="app.core.email"):
        SmtpEmailSender()
    assert any("SMTP provider selected but" in r.message for r in caplog.records)


def test_smtp_sender_no_warning_when_configured(monkeypatch, caplog):
    from app.core.email import SmtpEmailSender

    _set_smtp(monkeypatch)
    with caplog.at_level(logging.WARNING, logger="app.core.email"):
        SmtpEmailSender()
    assert not any(
        "SMTP provider selected but" in r.message for r in caplog.records
    )


def test_resend_console_records_provider_resend(monkeypatch):
    from app.core import dev_mailbox
    from app.core.email import ResendWithConsoleSender

    recorded: list[dict] = []

    async def fake_record(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(dev_mailbox, "record_outbound_email", fake_record)

    exc = httpx.HTTPStatusError(
        "bad",
        request=httpx.Request("POST", "https://api.resend.com/emails"),
        response=httpx.Response(422),
    )
    monkeypatch.setattr(
        "app.core.email.ResendEmailSender.send", AsyncMock(side_effect=exc)
    )
    asyncio.run(
        ResendWithConsoleSender().send(to="x@example.com", subject="s", text="t")
    )
    assert recorded[0]["provider"] == "resend"


def test_resolve_email_sends_via_smtp_in_worker(monkeypatch):
    from app import worker

    _set_smtp(monkeypatch)
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp")
    # Skip the dev-mailbox capture block so the test needs no DB; we only assert
    # that the worker path actually invokes the SMTP transport.
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    with patch("app.core.email.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        worker._resolve_email(
            "x@example.com",
            "Order placed",
            "Your order is confirmed",
            html="<p>ok</p>",
        )
    assert mock_send.await_count == 1
    msg = mock_send.await_args.args[0]
    assert msg["To"] == "x@example.com"
    assert msg["Subject"] == "Order placed"
    assert msg.get_content_type() == "multipart/alternative"


def test_get_email_sender_returns_smtp_variants(monkeypatch):
    from app.core import email as email_mod

    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp")
    email_mod.get_email_sender.cache_clear()
    assert isinstance(email_mod.get_email_sender(), email_mod.SmtpEmailSender)

    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp+console")
    email_mod.get_email_sender.cache_clear()
    assert isinstance(email_mod.get_email_sender(), email_mod.SmtpWithConsoleSender)

    # Leave the cache clean for later tests (monkeypatch restores EMAIL_PROVIDER).
    email_mod.get_email_sender.cache_clear()
