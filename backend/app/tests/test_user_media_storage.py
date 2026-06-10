# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import pytest

from app.core.config import settings
from app.services.image_storage import (
    LocalImageStorage,
    get_user_media_storage,
)


@pytest.mark.asyncio
async def test_user_media_storage_local_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "MEDIA_LOCAL_DIR", str(tmp_path))
    storage = get_user_media_storage()
    assert isinstance(storage, LocalImageStorage)
    url = await storage.save("avatars/customer/1/abc.webp", b"data", "image/webp")
    assert url.endswith("avatars/customer/1/abc.webp")
    assert (tmp_path / "avatars/customer/1/abc.webp").read_bytes() == b"data"
