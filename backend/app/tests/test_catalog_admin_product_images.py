# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
"""Product image collection — service-level + HTTP endpoint tests."""

import io
from pathlib import Path

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import MasterProduct
from app.services import product_images as svc
from app.services.image_processing import ImageValidationError
from tests.conftest import _Stub


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (0, 128, 0)).save(buf, format="PNG")
    return buf.getvalue()


def _id(value: int | None) -> int:
    assert value is not None
    return value


async def _make_product(session: AsyncSession, sub_id: int) -> int:
    p = MasterProduct(subcategory_id=sub_id, slug="p1", base_price=10.0, is_active=True)
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return _id(p.id)


@pytest.mark.asyncio
async def test_add_uploaded_image_sets_cover(
    session: AsyncSession,
    seeded_subcategory: _Stub,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "IMAGE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "MEDIA_LOCAL_DIR", str(tmp_path))
    pid = await _make_product(session, seeded_subcategory.id)

    row = await svc.add_uploaded_image(session, pid, _png())
    assert row.position == 0
    assert row.source == "uploaded"
    assert row.url.startswith("/media/products/")
    refreshed = await session.get(MasterProduct, pid)
    assert refreshed is not None and refreshed.image_url == row.url  # cover synced


@pytest.mark.asyncio
async def test_add_external_url(session: AsyncSession, seeded_subcategory: _Stub) -> None:
    pid = await _make_product(session, seeded_subcategory.id)
    row = await svc.add_external_image(session, pid, "https://x.test/a.jpg")
    assert row.source == "external" and row.storage_key is None
    refreshed = await session.get(MasterProduct, pid)
    assert refreshed is not None and refreshed.image_url == "https://x.test/a.jpg"


@pytest.mark.asyncio
async def test_external_url_rejects_bad(
    session: AsyncSession, seeded_subcategory: _Stub
) -> None:
    pid = await _make_product(session, seeded_subcategory.id)
    with pytest.raises(ImageValidationError):
        await svc.add_external_image(session, pid, "ftp://x/y")


@pytest.mark.asyncio
async def test_twenty_image_cap(session: AsyncSession, seeded_subcategory: _Stub) -> None:
    pid = await _make_product(session, seeded_subcategory.id)
    for i in range(20):
        await svc.add_external_image(session, pid, f"https://x.test/{i}.jpg")
    with pytest.raises(svc.ProductImageLimitError):
        await svc.add_external_image(session, pid, "https://x.test/21.jpg")


@pytest.mark.asyncio
async def test_reorder_changes_cover(
    session: AsyncSession, seeded_subcategory: _Stub
) -> None:
    pid = await _make_product(session, seeded_subcategory.id)
    a = await svc.add_external_image(session, pid, "https://x.test/a.jpg")
    b = await svc.add_external_image(session, pid, "https://x.test/b.jpg")
    await svc.reorder_images(session, pid, [_id(b.id), _id(a.id)])
    refreshed = await session.get(MasterProduct, pid)
    assert refreshed is not None and refreshed.image_url == "https://x.test/b.jpg"


@pytest.mark.asyncio
async def test_delete_renumbers_and_resyncs(
    session: AsyncSession, seeded_subcategory: _Stub
) -> None:
    pid = await _make_product(session, seeded_subcategory.id)
    a = await svc.add_external_image(session, pid, "https://x.test/a.jpg")
    b = await svc.add_external_image(session, pid, "https://x.test/b.jpg")
    await svc.delete_image(session, pid, _id(a.id))
    remaining = await svc.list_images(session, pid)
    assert [r.position for r in remaining] == [0]
    assert remaining[0].id == b.id
    refreshed = await session.get(MasterProduct, pid)
    assert refreshed is not None and refreshed.image_url == "https://x.test/b.jpg"


@pytest.mark.asyncio
async def test_upload_endpoint_then_read_includes_images(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_subcategory: _Stub,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "IMAGE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "MEDIA_LOCAL_DIR", str(tmp_path))

    create = await client.post(
        "/api/v1/catalog/admin/products",
        headers=admin_auth_headers,
        json={"subcategory_id": seeded_subcategory.id, "name": "Img Prod", "base_price": 5.0},
    )
    assert create.status_code == 200, create.text
    pid = create.json()["id"]

    up = await client.post(
        f"/api/v1/catalog/admin/products/{pid}/images/upload",
        headers=admin_auth_headers,
        files={"file": ("p.png", _png(), "image/png")},
    )
    assert up.status_code == 200, up.text
    assert up.json()["source"] == "uploaded"

    read = await client.get(
        f"/api/v1/catalog/admin/products/{pid}", headers=admin_auth_headers
    )
    body = read.json()
    assert len(body["images"]) == 1
    assert body["image_url"] == body["images"][0]["url"]


@pytest.mark.asyncio
async def test_upload_rejects_non_image(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_subcategory: _Stub,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "IMAGE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "MEDIA_LOCAL_DIR", str(tmp_path))
    create = await client.post(
        "/api/v1/catalog/admin/products",
        headers=admin_auth_headers,
        json={"subcategory_id": seeded_subcategory.id, "name": "X", "base_price": 1.0},
    )
    pid = create.json()["id"]
    up = await client.post(
        f"/api/v1/catalog/admin/products/{pid}/images/upload",
        headers=admin_auth_headers,
        files={"file": ("p.txt", b"not an image", "image/png")},
    )
    assert up.status_code == 422


@pytest.mark.asyncio
async def test_add_url_reorder_delete_flow(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    seeded_subcategory: _Stub,
) -> None:
    create = await client.post(
        "/api/v1/catalog/admin/products",
        headers=admin_auth_headers,
        json={"subcategory_id": seeded_subcategory.id, "name": "Y", "base_price": 1.0},
    )
    pid = create.json()["id"]
    r1 = await client.post(
        f"/api/v1/catalog/admin/products/{pid}/images/url",
        headers=admin_auth_headers, json={"url": "https://x.test/1.jpg"},
    )
    r2 = await client.post(
        f"/api/v1/catalog/admin/products/{pid}/images/url",
        headers=admin_auth_headers, json={"url": "https://x.test/2.jpg"},
    )
    id1, id2 = r1.json()["id"], r2.json()["id"]
    order = await client.patch(
        f"/api/v1/catalog/admin/products/{pid}/images/order",
        headers=admin_auth_headers, json={"image_ids": [id2, id1]},
    )
    assert [i["id"] for i in order.json()] == [id2, id1]
    dele = await client.delete(
        f"/api/v1/catalog/admin/products/{pid}/images/{id2}", headers=admin_auth_headers
    )
    assert dele.status_code == 200
