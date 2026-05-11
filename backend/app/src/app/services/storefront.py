# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Build the tree-shaped storefront payload for one store.

One joined `select` pulls every available inventory row plus its product,
subcategory, category, and service. Four batched `IN (...)` lookups
fetch translations (with English fallback). Python then groups the rows
into the response tree. No per-row sub-queries — translation cost is
constant in the number of inventory rows.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import (
    Category,
    CategoryTranslation,
    LanguageCode,
    MasterProduct,
    MasterProductTranslation,
    Service,
    ServiceTranslation,
    Subcategory,
    SubcategoryTranslation,
)
from app.models.store import StoreInventory
from app.schemas.storefront import (
    StorefrontCategory,
    StorefrontItem,
    StorefrontResponse,
    StorefrontService,
    StorefrontSubcategory,
)
from app.schemas.stores import StoreRead

_EN = LanguageCode.English.value

T = TypeVar("T")


def _coalesce(*values: T | None) -> T | None:
    for v in values:
        if v is not None:
            return v
    return None


async def _translation_map(
    session: AsyncSession,
    model: type,
    fk_attr: str,
    ids: Iterable[int],
    lang: str,
) -> dict[int, object]:
    """Return {fk_id: translation_row} for `ids`, with English fallback.

    Two queries max (one for `lang`, one for English fallback); skipped
    when `lang == 'en'`.
    """
    id_list = list({i for i in ids if i is not None})
    out: dict[int, object] = {}
    if not id_list:
        return out

    if lang != _EN:
        result = await session.exec(
            select(model).where(
                getattr(model, fk_attr).in_(id_list),
                getattr(model, "language_code") == lang,
            )
        )
        for row in result.all():
            out[getattr(row, fk_attr)] = row

    missing = [i for i in id_list if i not in out]
    if missing:
        result = await session.exec(
            select(model).where(
                getattr(model, fk_attr).in_(missing),
                getattr(model, "language_code") == _EN,
            )
        )
        for row in result.all():
            out[getattr(row, fk_attr)] = row
    return out


async def build_storefront(
    session: AsyncSession,
    store_read: StoreRead,
    store_id: int,
    lang: str,
) -> StorefrontResponse:
    """Pull the store's available inventory, join its catalog spine, and
    return a tree grouped by service → category → subcategory.

    Out-of-stock / unavailable inventory rows are excluded server-side,
    matching the existing `list_store_inventory` filter.
    """
    join_stmt = (
        select(StoreInventory, MasterProduct, Subcategory, Category, Service)
        .join(MasterProduct, MasterProduct.id == StoreInventory.product_id)  # type: ignore[arg-type]
        .join(Subcategory, Subcategory.id == MasterProduct.subcategory_id)  # type: ignore[arg-type]
        .join(Category, Category.id == Subcategory.category_id)  # type: ignore[arg-type]
        .join(Service, Service.id == Category.service_id)  # type: ignore[arg-type]
        .where(
            StoreInventory.store_id == store_id,
            StoreInventory.is_available,
        )
    )
    rows = list((await session.exec(join_stmt)).all())

    if not rows:
        return StorefrontResponse(store=store_read, services=[])

    product_t = await _translation_map(
        session, MasterProductTranslation, "master_product_id",
        (p.id for _i, p, _s, _c, _sv in rows if p.id is not None), lang,
    )
    sub_t = await _translation_map(
        session, SubcategoryTranslation, "subcategory_id",
        (s.id for _i, _p, s, _c, _sv in rows if s.id is not None), lang,
    )
    cat_t = await _translation_map(
        session, CategoryTranslation, "category_id",
        (c.id for _i, _p, _s, c, _sv in rows if c.id is not None), lang,
    )
    svc_t = await _translation_map(
        session, ServiceTranslation, "service_id",
        (sv.id for _i, _p, _s, _c, sv in rows if sv.id is not None), lang,
    )

    # service_id -> {entity, categories: {cat_id -> {entity, subs: {sub_id -> {entity, items[]}}}}}
    services: dict[int, dict] = {}

    for inv, product, sub, cat, svc in rows:
        assert inv.id is not None
        assert product.id is not None
        assert sub.id is not None
        assert cat.id is not None
        assert svc.id is not None

        svc_node = services.get(svc.id)
        if svc_node is None:
            svc_translation = svc_t.get(svc.id)
            svc_node = {
                "entity": svc,
                "name": getattr(svc_translation, "name", None) or svc.slug,
                "categories": {},
            }
            services[svc.id] = svc_node

        cat_node = svc_node["categories"].get(cat.id)
        if cat_node is None:
            cat_translation = cat_t.get(cat.id)
            cat_node = {
                "entity": cat,
                "name": getattr(cat_translation, "name", None) or cat.slug,
                "subcategories": {},
            }
            svc_node["categories"][cat.id] = cat_node

        sub_node = cat_node["subcategories"].get(sub.id)
        if sub_node is None:
            sub_translation = sub_t.get(sub.id)
            sub_node = {
                "entity": sub,
                "name": getattr(sub_translation, "name", None) or sub.slug,
                "items": [],
            }
            cat_node["subcategories"][sub.id] = sub_node

        p_translation = product_t.get(product.id)
        sub_node["items"].append(StorefrontItem(
            inventory_id=inv.id,
            product_id=product.id,
            product_slug=product.slug,
            product_name=getattr(p_translation, "name", None) or product.slug,
            image_url=product.image_url,
            description=getattr(p_translation, "description", None),
            price=float(inv.price),
            stock=inv.stock,
        ))

    out_services: list[StorefrontService] = []
    for svc_node in services.values():
        svc_entity: Service = svc_node["entity"]
        out_categories: list[StorefrontCategory] = []
        for cat_node in svc_node["categories"].values():
            cat_entity: Category = cat_node["entity"]
            out_subs: list[StorefrontSubcategory] = []
            for sub_node in cat_node["subcategories"].values():
                sub_entity: Subcategory = sub_node["entity"]
                items: list[StorefrontItem] = sorted(
                    sub_node["items"], key=lambda i: i.product_name.lower()
                )
                out_subs.append(StorefrontSubcategory(
                    id=sub_entity.id,  # type: ignore[arg-type]
                    slug=sub_entity.slug,
                    name=sub_node["name"],
                    sort_order=sub_entity.sort_order,
                    items=items,
                ))
            out_subs.sort(key=lambda s: (s.sort_order, s.id))
            out_categories.append(StorefrontCategory(
                id=cat_entity.id,  # type: ignore[arg-type]
                slug=cat_entity.slug,
                name=cat_node["name"],
                sort_order=cat_entity.sort_order,
                subcategories=out_subs,
            ))
        out_categories.sort(key=lambda c: (c.sort_order, c.id))
        out_services.append(StorefrontService(
            id=svc_entity.id,  # type: ignore[arg-type]
            slug=svc_entity.slug,
            name=svc_node["name"],
            sort_order=svc_entity.sort_order,
            categories=out_categories,
        ))
    out_services.sort(key=lambda s: (s.sort_order, s.id))

    return StorefrontResponse(store=store_read, services=out_services)
