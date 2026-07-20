# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest

from app.core.email_render import render_email


@pytest.mark.parametrize(
    "event_key",
    [
        "account_deactivated",
        "account_deleted",
        "account_suspended",
        "account_reactivated",
        "account_removed",
    ],
)
def test_account_status_templates_render(event_key: str) -> None:
    # StrictUndefined: this raises if a template references a var we do not pass.
    payload = render_email(event_key, {"first_name": "Asha"}, lang="en")
    assert payload.subject
    assert "Asha" in payload.text
    assert payload.html


def test_dispatch_is_importable() -> None:
    from app.services.account_emails import dispatch_account_status_email

    assert callable(dispatch_account_status_email)
