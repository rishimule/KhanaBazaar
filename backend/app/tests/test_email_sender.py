# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
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
