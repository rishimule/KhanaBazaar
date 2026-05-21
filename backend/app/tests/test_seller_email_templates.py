# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Unit tests for the seller-lifecycle email Celery tasks.

Each test patches `_resolve_email` and invokes the task directly to verify the
rendered subject + HTML contain the expected variables and CTA URLs.
"""

from unittest.mock import patch


def _capture():
    cap: dict[str, object] = {}

    def fake_resolve(to, subject, body, *, html=None, reply_to=None):
        cap["to"] = to
        cap["subject"] = subject
        cap["body"] = body
        cap["html"] = html
        cap["reply_to"] = reply_to

    return cap, fake_resolve


def test_seller_approved_email_renders_dashboard_cta():
    cap, fake = _capture()
    with patch("app.worker._resolve_email", side_effect=fake):
        from app.worker import send_seller_approved_async

        send_seller_approved_async("seller@example.com", "Sample Mart")

    assert cap["to"] == "seller@example.com"
    assert "[Khana Bazaar]" in cap["subject"]
    assert "approved" in cap["subject"].lower()
    assert "Sample Mart" in cap["html"]
    assert "/seller" in cap["html"]
    assert "Sample Mart" in cap["body"]
