# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from jinja2 import UndefinedError

from app.core.email_render import EmailPayload, render_email


def test_render_email_returns_subject_preheader_html_text():
    payload = render_email("_smoke", {"name": "Ravi", "total": 1234.5}, lang="en")
    assert isinstance(payload, EmailPayload)
    assert payload.subject == "[Khana Bazaar] Smoke Ravi"
    assert payload.preheader == "preheader for Ravi"
    assert "Hello Ravi" in payload.html
    assert "₹1,234.50" in payload.html
    assert "Hello Ravi" in payload.text
    assert "Khana Bazaar" in payload.html
    assert "{{ " not in payload.html
    assert "{{ " not in payload.text


def test_render_email_raises_on_missing_required_var():
    with pytest.raises(UndefinedError):
        render_email("_smoke", {"total": 0}, lang="en")


def test_render_email_falls_back_to_default_lang_when_locale_dir_missing():
    payload = render_email("_smoke", {"name": "A", "total": 0}, lang="hi")
    assert "Hello A" in payload.html
