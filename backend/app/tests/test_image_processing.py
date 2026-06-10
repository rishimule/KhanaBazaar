# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import io
from pathlib import Path

import pytest
from PIL import Image

from app.services.image_processing import (
    ImageValidationError,
    process_image,
    validate_external_url,
)


def _png_bytes(w: int = 50, h: int = 50, mode: str = "RGB") -> bytes:
    img = Image.new(mode, (w, h), color=(255, 0, 0) if mode == "RGB" else (255, 0, 0, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_process_image_reencodes_to_webp() -> None:
    data, key = process_image(_png_bytes())
    assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    assert len(key) == 64  # sha256 hex
    out = Image.open(io.BytesIO(data))
    assert out.format == "WEBP"


def test_process_image_caps_dimension() -> None:
    from app.core.config import settings

    data, _ = process_image(_png_bytes(4000, 2000))
    out = Image.open(io.BytesIO(data))
    # A 4000px-wide input is downscaled to exactly the configured cap, whatever it is.
    assert max(out.size) == settings.IMAGE_MAX_DIMENSION_PX


def test_process_image_preserves_alpha() -> None:
    data, _ = process_image(_png_bytes(mode="RGBA"))
    out = Image.open(io.BytesIO(data))
    assert out.mode in ("RGBA", "LA")


def test_process_image_rejects_non_image() -> None:
    with pytest.raises(ImageValidationError):
        process_image(b"this is not an image")


def test_process_image_rejects_oversized_pixels(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "IMAGE_MAX_PIXELS", 1000)  # 1000 px total
    with pytest.raises(ImageValidationError):
        process_image(_png_bytes(100, 100))  # 10_000 px > 1000


def test_validate_external_url_accepts_https() -> None:
    assert validate_external_url("https://example.com/a.jpg") == "https://example.com/a.jpg"


@pytest.mark.parametrize("bad", ["", "ftp://x/y", "not a url", "javascript:alert(1)"])
def test_validate_external_url_rejects_bad(bad: str) -> None:
    with pytest.raises(ImageValidationError):
        validate_external_url(bad)


@pytest.mark.asyncio
async def test_local_storage_save_and_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.image_storage import LocalImageStorage

    store = LocalImageStorage(str(tmp_path), "/media")
    url = await store.save("products/abc.webp", b"hello", "image/webp")
    assert url == "/media/products/abc.webp"
    assert (tmp_path / "products" / "abc.webp").read_bytes() == b"hello"
    await store.delete("products/abc.webp")
    assert not (tmp_path / "products" / "abc.webp").exists()
    # delete is idempotent
    await store.delete("products/abc.webp")


def test_get_image_storage_returns_local_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings
    from app.services.image_storage import LocalImageStorage, get_image_storage

    monkeypatch.setattr(settings, "IMAGE_STORAGE_BACKEND", "local")
    assert isinstance(get_image_storage(), LocalImageStorage)
