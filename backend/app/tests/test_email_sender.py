# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import asyncio
from pathlib import Path

import httpx
import respx

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
