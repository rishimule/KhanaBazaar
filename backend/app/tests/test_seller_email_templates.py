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


def test_seller_rejected_email_renders_reason_and_resubmit_cta():
    cap, fake = _capture()
    with patch("app.worker._resolve_email", side_effect=fake):
        from app.worker import send_seller_rejected_async

        send_seller_rejected_async(
            "seller@example.com", "Sample Mart", "Documents missing"
        )

    assert cap["to"] == "seller@example.com"
    assert "[Khana Bazaar]" in cap["subject"]
    assert "Documents missing" in cap["html"]
    assert "Documents missing" in cap["body"]
    assert "/seller/signup" in cap["html"]
    assert "/seller/signup" in cap["body"]


def test_seller_application_submitted_renders_to_support_inbox():
    cap, fake = _capture()
    fake_ctx = {
        "business_name": "Sample Mart",
        "applicant_email": "owner@example.com",
        "submitted_at": "2026-05-21 10:00 UTC",
    }
    with (
        patch("app.worker._resolve_email", side_effect=fake),
        patch(
            "app.worker._load_seller_application_context", return_value=fake_ctx
        ),
    ):
        from app.worker import send_seller_application_submitted_async

        send_seller_application_submitted_async(123)

    assert "Sample Mart" in cap["subject"]
    assert "owner@example.com" in cap["html"]
    assert "/admin/sellers" in cap["html"]
    assert cap["reply_to"] == "owner@example.com"


def test_seller_application_submitted_skips_when_ctx_empty():
    cap, fake = _capture()
    with (
        patch("app.worker._resolve_email", side_effect=fake),
        patch("app.worker._load_seller_application_context", return_value={}),
    ):
        from app.worker import send_seller_application_submitted_async

        send_seller_application_submitted_async(999)

    assert cap == {}


def test_seller_rejected_email_with_empty_reason_uses_fallback():
    cap, fake = _capture()
    with patch("app.worker._resolve_email", side_effect=fake):
        from app.worker import send_seller_rejected_async

        send_seller_rejected_async("seller@example.com", "Sample Mart", "")

    assert "Not specified" in cap["html"]
