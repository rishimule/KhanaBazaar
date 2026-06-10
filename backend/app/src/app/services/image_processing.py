# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Validate + normalize uploaded product images (no I/O).

`process_image` re-encodes any accepted input to a single WebP rendition:
honors EXIF orientation then strips metadata, preserves alpha, caps the
longest side, and guards against decompression bombs. Returns the WebP
bytes plus the sha256 hex of those bytes (used as the content-addressed
storage key). `validate_external_url` only checks URL *shape* — it NEVER
fetches the URL (SSRF defense).
"""
from __future__ import annotations

import hashlib
import io
from urllib.parse import urlparse

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


class ImageValidationError(Exception):
    """Raised when an upload or URL fails validation. `str(exc)` is the code."""


def process_image(raw: bytes) -> tuple[bytes, str]:
    """Validate + re-encode to WebP. Returns (webp_bytes, sha256_hex)."""
    max_bytes = settings.IMAGE_MAX_UPLOAD_MB * 1024 * 1024
    if len(raw) > max_bytes:
        raise ImageValidationError("file_too_large")

    # Decompression-bomb guard — Pillow raises DecompressionBombError past this.
    Image.MAX_IMAGE_PIXELS = settings.IMAGE_MAX_PIXELS
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = (probe.format or "").upper()
            if fmt not in ALLOWED_FORMATS:
                raise ImageValidationError("unsupported_format")
            w, h = probe.size
            if w * h > settings.IMAGE_MAX_PIXELS:
                raise ImageValidationError("image_too_large")

        with Image.open(io.BytesIO(raw)) as src_img:
            im: Image.Image = ImageOps.exif_transpose(src_img)  # orientation, drop EXIF
            if im.mode == "P":
                im = im.convert("RGBA")
            elif im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA" if "A" in im.mode else "RGB")
            max_dim = settings.IMAGE_MAX_DIMENSION_PX
            if max(im.size) > max_dim:
                im.thumbnail((max_dim, max_dim))
            out = io.BytesIO()
            im.save(out, format="WEBP", quality=82, method=4)
            data = out.getvalue()
    except ImageValidationError:
        raise
    except Image.DecompressionBombError as exc:
        raise ImageValidationError("image_too_large") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageValidationError("invalid_image") from exc

    return data, hashlib.sha256(data).hexdigest()


def validate_external_url(url: str) -> str:
    """Validate the *shape* of an external image URL. Never fetches it."""
    url = (url or "").strip()
    if not url or len(url) > 2048:
        raise ImageValidationError("invalid_url")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ImageValidationError("invalid_url")
    return url
