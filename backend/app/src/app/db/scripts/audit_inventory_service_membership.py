# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""One-shot audit: log any storeinventory rows whose product belongs to
a service NOT in the owning seller's approved services. Does not modify
data — purely a diagnostic for the bulk-inventory rollout (2026-05-05).

Run from `backend/app`:
    uv run python -m app.db.scripts.audit_inventory_service_membership
"""

import asyncio
import logging

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.session import engine
from app.models.catalog import Category, MasterProduct, Subcategory
from app.models.profile import SellerProfileService
from app.models.store import Store, StoreInventory

logger = logging.getLogger("audit_inventory_service_membership")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def audit() -> int:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        stmt = (
            select(
                StoreInventory.id,
                StoreInventory.store_id,
                StoreInventory.product_id,
                Store.seller_profile_id,
                Category.service_id,
            )
            .join(Store, Store.id == StoreInventory.store_id)  # type: ignore[arg-type]
            .join(MasterProduct, MasterProduct.id == StoreInventory.product_id)  # type: ignore[arg-type]
            .join(Subcategory, Subcategory.id == MasterProduct.subcategory_id)  # type: ignore[arg-type]
            .join(Category, Category.id == Subcategory.category_id)  # type: ignore[arg-type]
        )
        rows = list((await session.exec(stmt)).all())

        approved_stmt = select(
            SellerProfileService.seller_profile_id,
            SellerProfileService.service_id,
        )
        approved_pairs = list((await session.exec(approved_stmt)).all())
        approved_by_profile: dict[int, set[int]] = {}
        for profile_id, svc_id in approved_pairs:
            approved_by_profile.setdefault(profile_id, set()).add(svc_id)

        violations = 0
        for inv_id, store_id, product_id, profile_id, service_id in rows:
            approved = approved_by_profile.get(profile_id, set())
            if service_id not in approved:
                violations += 1
                logger.warning(
                    "violation: inventory_id=%s store_id=%s product_id=%s "
                    "profile_id=%s product_service_id=%s approved_services=%s",
                    inv_id,
                    store_id,
                    product_id,
                    profile_id,
                    service_id,
                    sorted(approved),
                )
        logger.info(
            "audit complete - %d violation(s) across %d rows",
            violations,
            len(rows),
        )
        return violations


if __name__ == "__main__":
    asyncio.run(audit())
