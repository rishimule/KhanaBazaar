# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import io

import pytest
from PIL import Image
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import MasterProduct
from app.services import product_images as svc
from app.services.image_processing import ImageValidationError


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (0, 128, 0)).save(buf, format="PNG")
    return buf.getvalue()


async def _make_product(session: AsyncSession, sub_id: int) -> MasterProduct:
    p = MasterProduct(subcategory_id=sub_id, slug="p1", base_price=10.0, is_active=True)
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_add_uploaded_image_sets_cover(
    session: AsyncSession, seeded_subcategory, monkeypatch, tmp_path
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "IMAGE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "MEDIA_LOCAL_DIR", str(tmp_path))
    p = await _make_product(session, seeded_subcategory.id)

    row = await svc.add_uploaded_image(session, p.id, _png())
    assert row.position == 0
    assert row.source == "uploaded"
    assert row.url.startswith("/media/products/")
    refreshed = await session.get(MasterProduct, p.id)
    assert refreshed.image_url == row.url  # cover synced


@pytest.mark.asyncio
async def test_add_external_url(session: AsyncSession, seeded_subcategory) -> None:
    p = await _make_product(session, seeded_subcategory.id)
    row = await svc.add_external_image(session, p.id, "https://x.test/a.jpg")
    assert row.source == "external" and row.storage_key is None
    refreshed = await session.get(MasterProduct, p.id)
    assert refreshed.image_url == "https://x.test/a.jpg"


@pytest.mark.asyncio
async def test_external_url_rejects_bad(session: AsyncSession, seeded_subcategory) -> None:
    p = await _make_product(session, seeded_subcategory.id)
    with pytest.raises(ImageValidationError):
        await svc.add_external_image(session, p.id, "ftp://x/y")


@pytest.mark.asyncio
async def test_twenty_image_cap(session: AsyncSession, seeded_subcategory) -> None:
    p = await _make_product(session, seeded_subcategory.id)
    for i in range(20):
        await svc.add_external_image(session, p.id, f"https://x.test/{i}.jpg")
    with pytest.raises(svc.ProductImageLimitError):
        await svc.add_external_image(session, p.id, "https://x.test/21.jpg")


@pytest.mark.asyncio
async def test_reorder_changes_cover(session: AsyncSession, seeded_subcategory) -> None:
    p = await _make_product(session, seeded_subcategory.id)
    a = await svc.add_external_image(session, p.id, "https://x.test/a.jpg")
    b = await svc.add_external_image(session, p.id, "https://x.test/b.jpg")
    await svc.reorder_images(session, p.id, [b.id, a.id])
    refreshed = await session.get(MasterProduct, p.id)
    assert refreshed.image_url == "https://x.test/b.jpg"


@pytest.mark.asyncio
async def test_delete_renumbers_and_resyncs(session: AsyncSession, seeded_subcategory) -> None:
    p = await _make_product(session, seeded_subcategory.id)
    a = await svc.add_external_image(session, p.id, "https://x.test/a.jpg")
    b = await svc.add_external_image(session, p.id, "https://x.test/b.jpg")
    await svc.delete_image(session, p.id, a.id)
    remaining = await svc.list_images(session, p.id)
    assert [r.position for r in remaining] == [0]
    assert remaining[0].id == b.id
    refreshed = await session.get(MasterProduct, p.id)
    assert refreshed.image_url == "https://x.test/b.jpg"
