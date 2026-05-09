# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""FastAPI dependency for resolving request locale."""

from fastapi import Header

from app.utils.locale import parse_accept_language


async def get_request_locale(
    accept_language: str | None = Header(default=None),
) -> str:
    return parse_accept_language(accept_language)
