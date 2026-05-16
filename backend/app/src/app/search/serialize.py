# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Pure builders that turn DB rows into Meilisearch documents."""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.catalog import (
    Category,
    CategoryTranslation,
    LanguageCode,
    MasterProduct,
    MasterProductTranslation,
    Service,
    Subcategory,
    SubcategoryTranslation,
)
from app.models.store import Store, StoreInventory

_LOCALES = [c.value for c in LanguageCode]


async def build_product_document(
    session: AsyncSession, product_id: int
) -> dict[str, Any] | None:
    product = (
        await session.execute(select(MasterProduct).where(MasterProduct.id == product_id))
    ).scalar_one_or_none()
    if product is None:
        return None

    translations_by_locale: dict[str, MasterProductTranslation] = {}
    for t in (
        await session.execute(
            select(MasterProductTranslation).where(
                MasterProductTranslation.master_product_id == product_id
            )
        )
    ).scalars():
        translations_by_locale[t.language_code] = t

    en_t = translations_by_locale.get("en")

    def name_for(locale: str) -> str:
        t = translations_by_locale.get(locale)
        if t and t.name:
            return t.name
        return en_t.name if en_t else product.slug

    def desc_for(locale: str) -> str:
        t = translations_by_locale.get(locale)
        if t and t.description:
            return t.description
        return en_t.description if en_t else ""

    subcat = (
        await session.execute(select(Subcategory).where(Subcategory.id == product.subcategory_id))
    ).scalar_one()
    cat = (
        await session.execute(select(Category).where(Category.id == subcat.category_id))
    ).scalar_one()
    service = (
        await session.execute(select(Service).where(Service.id == cat.service_id))
    ).scalar_one()

    sub_t_en = (
        await session.execute(
            select(SubcategoryTranslation).where(
                SubcategoryTranslation.subcategory_id == subcat.id,
                SubcategoryTranslation.language_code == "en",
            )
        )
    ).scalar_one_or_none()
    cat_t_en = (
        await session.execute(
            select(CategoryTranslation).where(
                CategoryTranslation.category_id == cat.id,
                CategoryTranslation.language_code == "en",
            )
        )
    ).scalar_one_or_none()

    inv_rows = (
        await session.execute(
            select(StoreInventory, Store)
            .join(Store, Store.id == StoreInventory.store_id)
            .where(
                StoreInventory.product_id == product_id,
                Store.is_active.is_(True),
            )
        )
    ).all()

    per_store_offers: list[dict[str, Any]] = []
    store_ids: list[int] = []
    for inv, store in inv_rows:
        per_store_offers.append(
            {
                "store_id": store.id,
                "price": float(inv.price),
                "stock": int(inv.stock),
                "is_available": bool(inv.is_available),
            }
        )
        store_ids.append(store.id)

    available_prices = [
        o["price"] for o in per_store_offers if o["is_available"] and o["stock"] > 0
    ]
    if available_prices:
        min_price = min(available_prices)
        max_price = max(available_prices)
        in_stock_anywhere = True
    else:
        min_price = float(product.base_price)
        max_price = float(product.base_price)
        in_stock_anywhere = False

    doc: dict[str, Any] = {
        "id": product.id,
        "slug": product.slug,
        "image_url": product.image_url,
        "base_price": float(product.base_price),
        "brand": product.brand,
        "unit": product.unit,
        "is_active": bool(product.is_active),
        "service_id": service.id,
        "service_slug": service.slug,
        "category_id": cat.id,
        "category_slug": cat.slug,
        "subcategory_id": subcat.id,
        "subcategory_slug": subcat.slug,
        "store_ids": store_ids,
        "per_store_offers": per_store_offers,
        "min_price": min_price,
        "max_price": max_price,
        "in_stock_anywhere": in_stock_anywhere,
        "category_name_en": cat_t_en.name if cat_t_en else cat.slug,
        "subcategory_name_en": sub_t_en.name if sub_t_en else subcat.slug,
        "updated_at": int(time.time()),
    }
    for locale in _LOCALES:
        doc[f"name_{locale}"] = name_for(locale)
        doc[f"description_{locale}"] = desc_for(locale)
    return doc


async def build_store_document(
    session: AsyncSession, store_id: int
) -> dict[str, Any] | None:
    """Build a stores-index doc. Coordinates come from joined Address."""
    row = (
        await session.execute(
            select(Store, Address)
            .join(Address, Address.id == Store.address_id)
            .where(Store.id == store_id)
        )
    ).first()
    if row is None:
        return None
    store, address = row
    if not store.is_active:
        return None

    # Distinct services across this store's active inventory
    rows = (
        await session.execute(
            select(Category.service_id)
            .select_from(StoreInventory)
            .join(MasterProduct, MasterProduct.id == StoreInventory.product_id)
            .join(Subcategory, Subcategory.id == MasterProduct.subcategory_id)
            .join(Category, Category.id == Subcategory.category_id)
            .where(
                StoreInventory.store_id == store_id,
                StoreInventory.is_available.is_(True),
            )
            .distinct()
        )
    ).all()
    service_ids = sorted({sid for (sid,) in rows})

    return {
        "id": store.id,
        "name": store.name,
        "service_ids": service_ids,
        "lat": float(address.latitude) if address.latitude is not None else None,
        "lng": float(address.longitude) if address.longitude is not None else None,
        "delivery_radius_km": float(store.delivery_radius_km),
        "is_active": bool(store.is_active),
    }


async def build_search_term_docs(session: AsyncSession) -> list[dict[str, Any]]:
    """Collect product/category/subcategory names per locale as autocomplete terms."""
    docs: list[dict[str, Any]] = []
    name_counts: dict[tuple[str, str], int] = {}
    for t in (await session.execute(select(MasterProductTranslation))).scalars():
        key = (t.name.strip().lower(), t.language_code)
        if not key[0]:
            continue
        name_counts[key] = name_counts.get(key, 0) + 1
    for (term, locale), weight in name_counts.items():
        docs.append(
            {
                "id": f"{term}_{locale}",
                "term": term,
                "locale": locale,
                "kind": "product_name",
                "weight": weight,
            }
        )
    for t in (await session.execute(select(CategoryTranslation))).scalars():
        term = t.name.strip().lower()
        if not term:
            continue
        docs.append(
            {
                "id": f"{term}_{t.language_code}_cat",
                "term": term,
                "locale": t.language_code,
                "kind": "category",
                "weight": 1,
            }
        )
    for t in (await session.execute(select(SubcategoryTranslation))).scalars():
        term = t.name.strip().lower()
        if not term:
            continue
        docs.append(
            {
                "id": f"{term}_{t.language_code}_sub",
                "term": term,
                "locale": t.language_code,
                "kind": "subcategory",
                "weight": 1,
            }
        )
    return docs
