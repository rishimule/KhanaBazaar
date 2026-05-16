# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Process-wide async Meilisearch client factory."""
from __future__ import annotations

from typing import Optional

from meilisearch_python_sdk import AsyncClient

from app.core.config import settings

_client: Optional[AsyncClient] = None


def get_meili_client() -> AsyncClient:
    """Return a process-wide AsyncClient pointed at the configured Meilisearch."""
    global _client
    if _client is None:
        _client = AsyncClient(settings.MEILI_URL, settings.MEILI_MASTER_KEY)
    return _client


async def close_meili_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
