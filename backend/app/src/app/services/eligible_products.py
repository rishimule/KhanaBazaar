# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Query products that a seller is allowed to add to their store
(filtered by their approved services), with localized names and an
already-in-inventory flag."""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import Category, MasterProduct, Service, Subcategory
from app.models.profile import SellerProfileService
from app.models.store import StoreInventory
from app.schemas.inventory import EligibleProduct
from app.services.catalog_translations import (
    load_category_translations,
    load_product_translations,
    load_service_translations,
    load_subcategory_translations,
    pick_translation,
)


async def list_eligible_products(
    session: AsyncSession,
    profile_id: int,
    store_id: int,
    lang: str,
) -> list[EligibleProduct]:
    svc_result = await session.exec(
        select(SellerProfileService.service_id).where(
            SellerProfileService.seller_profile_id == profile_id
        )
    )
    approved_service_ids = list(svc_result.all())
    if not approved_service_ids:
        return []

    stmt = (
        select(MasterProduct, Subcategory, Category)
        .join(Subcategory, Subcategory.id == MasterProduct.subcategory_id)  # type: ignore[arg-type]
        .join(Category, Category.id == Subcategory.category_id)  # type: ignore[arg-type]
        .join(Service, Service.id == Category.service_id)  # type: ignore[arg-type]
        .where(Category.service_id.in_(approved_service_ids))  # type: ignore[attr-defined]
        .where(MasterProduct.is_active == True)  # noqa: E712
        .where(Subcategory.is_active == True)  # noqa: E712
        .where(Category.is_active == True)  # noqa: E712
        .where(Service.is_active == True)  # noqa: E712
    )
    rows = list((await session.exec(stmt)).all())
    if not rows:
        return []

    product_ids = [p.id for p, _s, _c in rows if p.id is not None]
    sub_ids = [s.id for _p, s, _c in rows if s.id is not None]
    cat_ids = [c.id for _p, _s, c in rows if c.id is not None]
    svc_ids = list({c.service_id for _p, _s, c in rows})

    inv_result = await session.exec(
        select(StoreInventory.product_id).where(
            StoreInventory.store_id == store_id,
            StoreInventory.product_id.in_(product_ids),  # type: ignore[attr-defined]
        )
    )
    in_inventory_ids = set(inv_result.all())

    p_trans = await load_product_translations(session, product_ids)
    s_trans = await load_subcategory_translations(session, sub_ids)
    c_trans = await load_category_translations(session, cat_ids)
    sv_trans = await load_service_translations(session, svc_ids)

    out: list[EligibleProduct] = []
    for product, subcategory, category in rows:
        assert (
            product.id is not None
            and subcategory.id is not None
            and category.id is not None
        )
        prod_t = pick_translation(p_trans.get(product.id, []), lang)
        sub_t = pick_translation(s_trans.get(subcategory.id, []), lang)
        cat_t = pick_translation(c_trans.get(category.id, []), lang)
        svc_t = pick_translation(sv_trans.get(category.service_id, []), lang)

        out.append(
            EligibleProduct(
                id=product.id,
                name=prod_t.name if prod_t else f"product-{product.id}",
                base_price=product.base_price,
                subcategory_id=subcategory.id,
                subcategory_name=sub_t.name if sub_t else subcategory.slug,
                category_id=category.id,
                category_name=cat_t.name if cat_t else category.slug,
                service_id=category.service_id,
                service_name=svc_t.name
                if svc_t
                else f"service-{category.service_id}",
                in_inventory=product.id in in_inventory_ids,
            )
        )
    return out
