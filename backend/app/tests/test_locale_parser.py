# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest

from app.utils.locale import DEFAULT_LOCALE, SUPPORTED_LOCALES, parse_accept_language


@pytest.mark.parametrize(
    "header,expected",
    [
        ("hi-IN,hi;q=0.9,en;q=0.8", "hi"),
        ("en-US,en;q=0.9", "en"),
        ("mr", "mr"),
        ("gu-IN", "gu"),
        ("pa", "pa"),
        ("fr,de", "en"),  # unsupported → default
        ("", "en"),
        (None, "en"),
        ("   ", "en"),
        ("garbage;;;", "en"),
        ("xx-YY,hi", "hi"),  # skip unsupported, take next supported
    ],
)
def test_parse_accept_language(header: str | None, expected: str) -> None:
    assert parse_accept_language(header) == expected


def test_supported_locales_set() -> None:
    assert SUPPORTED_LOCALES == {"en", "hi", "mr", "gu", "pa"}
    assert DEFAULT_LOCALE == "en"
