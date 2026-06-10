# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Avatar (profile-picture) blob helpers shared by the customer (direct) and
seller (change-request) flows.

Validation + WebP encode reuses the product-image pipeline; blobs live in the
dedicated user-media bucket under `avatars/{subject}/{profile_id}/{sha}.webp`.
"""
from __future__ import annotations

import anyio

from app.core.config import settings
from app.services.image_processing import process_image
from app.services.image_storage import get_user_media_storage


async def process_and_store(
    raw: bytes, subject: str, profile_id: int
) -> tuple[str, str]:
    """Validate + downscale + WebP-encode `raw`, upload to the user-media bucket.

    `subject` is "customer" | "seller". Returns (public_url, storage_key).
    Raises `ImageValidationError` on bad input (caller maps to HTTP 422).
    """
    data, digest = await anyio.to_thread.run_sync(
        process_image, raw, settings.AVATAR_MAX_DIMENSION_PX
    )
    key = f"avatars/{subject}/{profile_id}/{digest}.webp"
    url = await get_user_media_storage().save(key, data, "image/webp")
    return url, key


async def delete_blob(storage_key: str | None) -> None:
    """Best-effort delete of an avatar blob; no-op when key is falsy."""
    if not storage_key:
        return
    await get_user_media_storage().delete(storage_key)
