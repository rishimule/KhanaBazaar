"""Locale resolution from HTTP Accept-Language header."""

from __future__ import annotations

SUPPORTED_LOCALES: set[str] = {"en", "hi", "mr", "gu", "pa"}
DEFAULT_LOCALE: str = "en"


def parse_accept_language(header: str | None) -> str:
    """Return first supported 2-letter tag from Accept-Language, or DEFAULT_LOCALE.

    Ignores q-weights for v1 — takes first supported tag in declared order.
    """
    if not header or not header.strip():
        return DEFAULT_LOCALE
    for raw in header.split(","):
        tag = raw.strip().split(";", 1)[0].strip()
        if not tag:
            continue
        primary = tag.split("-", 1)[0].lower()
        if primary in SUPPORTED_LOCALES:
            return primary
    return DEFAULT_LOCALE
