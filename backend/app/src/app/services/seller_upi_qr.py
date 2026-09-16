# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Seller UPI verification-QR blob helpers: validate + downscale +
WebP-encode a raw upload and store it in the dedicated user-media bucket
under `seller-upi-qr/{seller_profile_id}/{sha}.webp`.

Mirrors `store_logos.py` — same validation pipeline and user-media bucket,
keyed by seller profile rather than store.

NOTE: this image is an ADMIN VERIFICATION ARTIFACT. It is never rendered to
customers, because the payee it encodes is unreadable to us and would be a
second, unapproved payee in the pay panel. See the design spec §2.1.
"""
from __future__ import annotations

import logging

import anyio

from app.core.config import settings
from app.services.image_processing import process_image
from app.services.image_storage import get_user_media_storage

logger = logging.getLogger(__name__)


async def process_and_store(raw: bytes, seller_profile_id: int) -> tuple[str, str]:
    """Validate + downscale + WebP-encode `raw`, upload to the user-media bucket.

    Returns (public_url, storage_key). Raises `ImageValidationError` on bad
    input (caller maps to HTTP 422).
    """
    data, digest = await anyio.to_thread.run_sync(
        process_image, raw, settings.IMAGE_MAX_DIMENSION_PX
    )
    key = f"seller-upi-qr/{seller_profile_id}/{digest}.webp"
    url = await get_user_media_storage().save(key, data, "image/webp")
    return url, key


async def delete_blob(storage_key: str | None) -> None:
    """Best-effort delete of a UPI-QR blob; no-op when key is falsy.

    Never raises: a storage error here must not abort the surrounding DB
    transaction. A leaked blob is harmless — it is admin-only and unreferenced.
    """
    if not storage_key:
        return
    try:
        await get_user_media_storage().delete(storage_key)
    except Exception:
        logger.warning(
            "seller upi qr blob delete failed key=%s", storage_key, exc_info=True
        )
