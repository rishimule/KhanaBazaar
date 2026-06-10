# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Object storage for product images.

Two backends behind one protocol, selected by `IMAGE_STORAGE_BACKEND`:
- LocalImageStorage: writes under MEDIA_LOCAL_DIR, returns a relative
  `/media/...` URL served by FastAPI StaticFiles (dev/test).
- GCSImageStorage: uploads to a public bucket with a 1-year immutable
  Cache-Control, returns the public object URL (prod). Blocking google-cloud
  calls run in a threadpool.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

import anyio

from app.core.config import settings


class ImageStorage(Protocol):
    async def save(self, key: str, data: bytes, content_type: str) -> str: ...
    async def delete(self, key: str) -> None: ...


class LocalImageStorage:
    def __init__(self, base_dir: str, url_prefix: str) -> None:
        self._base = Path(base_dir)
        self._prefix = url_prefix.rstrip("/")

    async def save(self, key: str, data: bytes, content_type: str) -> str:
        path = self._base / key
        path.parent.mkdir(parents=True, exist_ok=True)
        await anyio.to_thread.run_sync(path.write_bytes, data)
        return f"{self._prefix}/{key}"

    async def delete(self, key: str) -> None:
        path = self._base / key
        try:
            await anyio.to_thread.run_sync(path.unlink)
        except FileNotFoundError:
            pass


class GCSImageStorage:
    def __init__(self, bucket: str, public_base_url: str = "") -> None:
        from google.cloud import storage  # type: ignore[attr-defined]

        self._bucket_name = bucket
        self._bucket = storage.Client().bucket(bucket)
        self._public_base = public_base_url.rstrip("/")

    async def save(self, key: str, data: bytes, content_type: str) -> str:
        def _upload() -> None:
            blob = self._bucket.blob(key)
            blob.cache_control = "public, max-age=31536000, immutable"
            blob.upload_from_string(data, content_type=content_type)

        await anyio.to_thread.run_sync(_upload)
        if self._public_base:
            return f"{self._public_base}/{key}"
        return f"https://storage.googleapis.com/{self._bucket_name}/{key}"

    async def delete(self, key: str) -> None:
        def _delete() -> None:
            from google.cloud.exceptions import NotFound

            try:
                self._bucket.blob(key).delete()
            except NotFound:
                pass

        await anyio.to_thread.run_sync(_delete)


def get_image_storage() -> ImageStorage:
    """Construct the storage backend for the current settings.

    Not cached: tests monkeypatch settings between cases, and admin uploads
    are rare so per-call construction is fine.
    """
    if settings.IMAGE_STORAGE_BACKEND == "gcs":
        return GCSImageStorage(settings.GCS_PRODUCT_IMAGES_BUCKET, settings.GCS_PUBLIC_BASE_URL)
    return LocalImageStorage(settings.MEDIA_LOCAL_DIR, settings.MEDIA_URL_PREFIX)
