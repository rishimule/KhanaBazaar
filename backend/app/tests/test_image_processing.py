# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import io

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
    data, _ = process_image(_png_bytes(4000, 2000))
    out = Image.open(io.BytesIO(data))
    assert max(out.size) <= 1600


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
