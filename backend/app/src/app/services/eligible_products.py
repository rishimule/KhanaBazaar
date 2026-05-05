"""Query products that a seller is allowed to add to their store
(filtered by their approved services), with localized names and an
already-in-inventory flag."""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import Category, MasterProduct, Subcategory
from app.models.profile import SellerProfileService
from app.models.store import StoreInventory
from app.schemas.inventory import EligibleProduct
from app.services.catalog_translations import (
    localized_category_translation,
    localized_product_translation,
    localized_service_translation,
    localized_subcategory_translation,
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
        .where(Category.service_id.in_(approved_service_ids))  # type: ignore[attr-defined]
    )
    rows = list((await session.exec(stmt)).all())
    if not rows:
        return []

    product_ids = [p.id for p, _s, _c in rows if p.id is not None]
    inv_result = await session.exec(
        select(StoreInventory.product_id).where(
            StoreInventory.store_id == store_id,
            StoreInventory.product_id.in_(product_ids),  # type: ignore[attr-defined]
        )
    )
    in_inventory_ids = set(inv_result.all())

    out: list[EligibleProduct] = []
    for product, subcategory, category in rows:
        assert (
            product.id is not None
            and subcategory.id is not None
            and category.id is not None
        )
        prod_t = await localized_product_translation(session, product.id, lang)
        sub_t = await localized_subcategory_translation(session, subcategory.id, lang)
        cat_t = await localized_category_translation(session, category.id, lang)
        svc_t = await localized_service_translation(
            session, category.service_id, lang
        )

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
