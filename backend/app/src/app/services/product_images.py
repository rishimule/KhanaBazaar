# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Image-collection operations for a master product.

position 0 is the cover; MasterProduct.image_url is kept in sync with it so
list/card/search surfaces (which read image_url) update automatically — and
because touching MasterProduct marks it dirty, the existing after_commit
search hook re-indexes on cover change with no extra wiring. Uploaded-object
deletion is reference-aware: the stored object is removed only when no other
row references the same content-hash key (content-addressed keys dedupe).
"""
from __future__ import annotations

import anyio
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import MasterProduct, MasterProductImage
from app.services.image_processing import process_image, validate_external_url
from app.services.image_storage import get_image_storage

MAX_IMAGES = 20


class ProductImageError(Exception):
    """str(exc) is a stable error code."""


class ProductNotFound(ProductImageError):
    pass


class ProductImageNotFound(ProductImageError):
    pass


class ProductImageLimitError(ProductImageError):
    pass


async def list_images(session: AsyncSession, product_id: int) -> list[MasterProductImage]:
    rows = await session.exec(
        select(MasterProductImage)
        .where(MasterProductImage.master_product_id == product_id)
        .order_by(MasterProductImage.position)  # type: ignore[arg-type]
    )
    return list(rows.all())


async def _require_product(session: AsyncSession, product_id: int) -> MasterProduct:
    prod = await session.get(MasterProduct, product_id)
    if prod is None:
        raise ProductNotFound("not_found")
    return prod


async def _resync_cover(session: AsyncSession, product_id: int) -> None:
    images = await list_images(session, product_id)
    cover = images[0].url if images else None
    prod = await session.get(MasterProduct, product_id)
    if prod is not None and prod.image_url != cover:
        prod.image_url = cover
        session.add(prod)


async def add_uploaded_image(
    session: AsyncSession, product_id: int, raw: bytes
) -> MasterProductImage:
    await _require_product(session, product_id)
    existing = await list_images(session, product_id)
    if len(existing) >= MAX_IMAGES:
        raise ProductImageLimitError("image_limit_reached")
    data, digest = await anyio.to_thread.run_sync(process_image, raw)
    key = f"products/{digest}.webp"
    url = await get_image_storage().save(key, data, "image/webp")
    row = MasterProductImage(
        master_product_id=product_id,
        position=len(existing),
        url=url,
        source="uploaded",
        storage_key=key,
    )
    session.add(row)
    await session.flush()
    await _resync_cover(session, product_id)
    await session.commit()
    await session.refresh(row)
    return row


async def add_external_image(
    session: AsyncSession, product_id: int, url: str
) -> MasterProductImage:
    await _require_product(session, product_id)
    clean = validate_external_url(url)
    existing = await list_images(session, product_id)
    if len(existing) >= MAX_IMAGES:
        raise ProductImageLimitError("image_limit_reached")
    row = MasterProductImage(
        master_product_id=product_id,
        position=len(existing),
        url=clean,
        source="external",
        storage_key=None,
    )
    session.add(row)
    await session.flush()
    await _resync_cover(session, product_id)
    await session.commit()
    await session.refresh(row)
    return row


async def reorder_images(
    session: AsyncSession, product_id: int, image_ids: list[int]
) -> list[MasterProductImage]:
    await _require_product(session, product_id)
    rows = await list_images(session, product_id)
    by_id = {r.id: r for r in rows}
    if set(image_ids) != set(by_id.keys()):
        raise ProductImageError("image_set_mismatch")
    for i, iid in enumerate(image_ids):
        r = by_id[iid]
        if r.position != i:
            r.position = i
            session.add(r)
    await session.flush()
    await _resync_cover(session, product_id)
    await session.commit()
    return await list_images(session, product_id)


async def delete_image(session: AsyncSession, product_id: int, image_id: int) -> None:
    row = await session.get(MasterProductImage, image_id)
    if row is None or row.master_product_id != product_id:
        raise ProductImageNotFound("not_found")
    source, key = row.source, row.storage_key
    await session.delete(row)
    await session.flush()
    remaining = await list_images(session, product_id)
    for i, r in enumerate(remaining):
        if r.position != i:
            r.position = i
            session.add(r)
    await _resync_cover(session, product_id)
    await session.commit()

    # Reference-aware object delete, AFTER the row is gone + committed.
    if source == "uploaded" and key:
        others = await session.exec(
            select(MasterProductImage.id).where(MasterProductImage.storage_key == key)
        )
        if others.first() is None:
            await get_image_storage().delete(key)
