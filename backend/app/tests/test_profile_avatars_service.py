# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import io

import pytest
from PIL import Image

from app.core.config import settings
from app.services.profile_avatars import delete_blob, process_and_store


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (800, 800), "blue").save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_process_and_store_writes_avatar(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "MEDIA_LOCAL_DIR", str(tmp_path))
    url, key = await process_and_store(_png(), "customer", 7)
    assert key.startswith("avatars/customer/7/")
    assert key.endswith(".webp")
    assert (tmp_path / key).exists()
    assert url.endswith(key)
    # downscaled to AVATAR_MAX_DIMENSION_PX (512)
    with Image.open(tmp_path / key) as im:
        assert max(im.size) == 512


@pytest.mark.asyncio
async def test_delete_blob_noop_on_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "MEDIA_LOCAL_DIR", str(tmp_path))
    await delete_blob(None)  # must not raise
    await delete_blob("")    # must not raise
