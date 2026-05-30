# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.stores import StorePauseBody


def test_pause_body_rejects_past_date():
    with pytest.raises(ValidationError):
        StorePauseBody(is_paused=True, paused_until=date.today() - timedelta(days=1))


def test_pause_body_accepts_today_and_future():
    StorePauseBody(is_paused=True, paused_until=date.today())
    StorePauseBody(is_paused=True, paused_until=date.today() + timedelta(days=7))


def test_pause_body_allows_no_date():
    body = StorePauseBody(is_paused=False)
    assert body.paused_until is None
    assert body.reason is None
