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
from app.models.profile import SellerProfileService
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

    # Seller profiles that have THIS product's service paused — used to flag
    # per-store offers as closed even when the store itself isn't fully paused.
    paused_profile_ids = {
        pid
        for (pid,) in (
            await session.execute(
                select(SellerProfileService.seller_profile_id).where(
                    SellerProfileService.service_id == service.id,
                    SellerProfileService.is_paused.is_(True),
                )
            )
        ).all()
    }

    per_store_offers: list[dict[str, Any]] = []
    store_ids: list[int] = []
    for inv, store in inv_rows:
        store_paused = bool(store.is_paused) or store.seller_profile_id in paused_profile_ids
        per_store_offers.append(
            {
                "store_id": store.id,
                "price": float(inv.price),
                "stock": int(inv.stock),
                "is_available": bool(inv.is_available),
                "store_paused": store_paused,
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
        "db_updated_at": int(product.updated_at.timestamp()),
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

    paused_rows = (
        await session.execute(
            select(SellerProfileService.service_id).where(
                SellerProfileService.seller_profile_id == store.seller_profile_id,
                SellerProfileService.is_paused.is_(True),
            )
        )
    ).all()
    paused_service_ids = sorted({sid for (sid,) in paused_rows})

    return {
        "id": store.id,
        "name": store.name,
        "service_ids": service_ids,
        "lat": float(address.latitude) if address.latitude is not None else None,
        "lng": float(address.longitude) if address.longitude is not None else None,
        "delivery_radius_km": float(store.delivery_radius_km),
        "is_active": bool(store.is_active),
        "is_paused": bool(store.is_paused),
        "paused_until": store.paused_until.isoformat() if store.paused_until else None,
        "paused_service_ids": paused_service_ids,
        "db_updated_at": int(store.updated_at.timestamp()),
    }


_TERM_ID_RE = __import__("re").compile(r"[^a-zA-Z0-9_-]+")


def _term_id(term: str, locale: str, kind_suffix: str = "") -> str:
    """Meilisearch primary keys must match [a-zA-Z0-9_-]+. Slugify accordingly."""
    slug = _TERM_ID_RE.sub("-", term.strip().lower()).strip("-")
    if not slug:
        slug = "x"
    return f"{slug}_{locale}{kind_suffix}"


async def build_search_term_docs(session: AsyncSession) -> list[dict[str, Any]]:
    """Collect product/category/subcategory names per locale as autocomplete terms."""
    docs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def push(term: str, locale: str, kind: str, weight: int, suffix: str = "") -> None:
        term = term.strip().lower()
        if not term:
            return
        doc_id = _term_id(term, locale, suffix)
        if doc_id in seen_ids:
            return
        seen_ids.add(doc_id)
        docs.append(
            {
                "id": doc_id,
                "term": term,
                "locale": locale,
                "kind": kind,
                "weight": weight,
            }
        )

    name_counts: dict[tuple[str, str], int] = {}
    for t in (await session.execute(select(MasterProductTranslation))).scalars():
        key = (t.name.strip().lower(), t.language_code)
        if not key[0]:
            continue
        name_counts[key] = name_counts.get(key, 0) + 1
    for (term, locale), weight in name_counts.items():
        push(term, locale, "product_name", weight)
    for t in (await session.execute(select(CategoryTranslation))).scalars():
        push(t.name, t.language_code, "category", 1, suffix="-cat")
    for t in (await session.execute(select(SubcategoryTranslation))).scalars():
        push(t.name, t.language_code, "subcategory", 1, suffix="-sub")
    return docs
