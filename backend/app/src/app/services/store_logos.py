# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Store-logo blob helpers: validate + downscale + WebP-encode a raw upload and
store it in the dedicated user-media bucket under
`store-logos/{store_id}/{sha}.webp`.

Mirrors `profile_avatars.py` (seller/customer avatars) — same validation
pipeline and user-media bucket, keyed by store rather than profile.
"""
from __future__ import annotations

import logging

import anyio

from app.core.config import settings
from app.services.image_processing import process_image
from app.services.image_storage import get_user_media_storage

logger = logging.getLogger(__name__)


async def process_and_store(raw: bytes, store_id: int) -> tuple[str, str]:
    """Validate + downscale + WebP-encode `raw`, upload to the user-media bucket.

    Returns (public_url, storage_key). Raises `ImageValidationError` on bad
    input (caller maps to HTTP 422).
    """
    data, digest = await anyio.to_thread.run_sync(
        process_image, raw, settings.STORE_LOGO_MAX_DIMENSION_PX
    )
    key = f"store-logos/{store_id}/{digest}.webp"
    url = await get_user_media_storage().save(key, data, "image/webp")
    return url, key


async def delete_blob(storage_key: str | None) -> None:
    """Best-effort delete of a store-logo blob; no-op when key is falsy.

    Never raises: a storage error here must not abort the surrounding DB
    transaction. A leaked blob is harmless; the card falls back to the initial.
    """
    if not storage_key:
        return
    try:
        await get_user_media_storage().delete(storage_key)
    except Exception:
        logger.warning(
            "store logo blob delete failed key=%s", storage_key, exc_info=True
        )
