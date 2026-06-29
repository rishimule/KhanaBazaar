# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from app.core.email_render import render_email


def test_seller_onboarding_request_email_renders():
    payload = render_email(
        "seller_onboarding_request",
        {
            "store_name": "Sharma Kirana",
            "contact_phone": "+919812345678",
            "contact_email": "sharma@example.com",
            "contact_address": "12 MG Road, Pune",
            "preferred_categories": "Grocery",
            "area_label": "Pune",
            "source": "home",
        },
        lang="en",
    )
    assert "Sharma Kirana" in payload.text
    assert "sharma@example.com" in payload.text
    assert "12 MG Road, Pune" in payload.text
    assert payload.subject
    assert payload.html


def test_seller_onboarding_request_email_handles_optional_blanks():
    payload = render_email(
        "seller_onboarding_request",
        {
            "store_name": "X",
            "contact_phone": "+919812345678",
            "contact_email": "a@b.com",
            "contact_address": "addr",
            "preferred_categories": None,
            "area_label": None,
            "source": None,
        },
        lang="en",
    )
    assert "—" in payload.text
