# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import io

from PIL import Image

from app.services.image_processing import process_image


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "red").save(buf, format="PNG")
    return buf.getvalue()


def test_process_image_respects_explicit_max_dimension():
    data, digest = process_image(_png(1000, 1000), max_dimension=512)
    with Image.open(io.BytesIO(data)) as out:
        assert max(out.size) == 512
    assert len(digest) == 64
