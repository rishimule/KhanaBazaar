# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Support relay email — sends to SUPPORT_EMAIL with customer as reply-to."""

from unittest.mock import patch


def test_support_email_dispatches_with_customer_reply_to() -> None:
    captured: dict[str, object] = {}

    def fake_resolve(to, subject, body, *, html=None, reply_to=None):
        captured["to"] = to
        captured["subject"] = subject
        captured["body"] = body
        captured["html"] = html
        captured["reply_to"] = reply_to

    with patch("app.worker._resolve_email", side_effect=fake_resolve):
        from app.worker import send_support_email

        send_support_email("user@example.com", "Order issue", "Help with order #42")

    assert captured["subject"].startswith("[Support] Order issue")
    assert captured["reply_to"] == "user@example.com"
    assert "Help with order #42" in captured["html"]
    assert "Help with order #42" in captured["body"]
    from app.core.config import settings

    assert captured["to"] == settings.SUPPORT_EMAIL
