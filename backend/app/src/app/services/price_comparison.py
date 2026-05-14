# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Price comparison service.

`rank_candidates` is a pure function (no DB) -- easily unit tested.
`find_alternatives` is the session-bound entrypoint that builds candidates
from PostGIS + inventory data, then delegates ranking to `rank_candidates`.
"""
from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import MasterProductTranslation
from app.models.store import Store, StoreInventory
from app.schemas.price_comparison import ComparisonAlternative, ComparisonItem

MAX_ALTERNATIVES = 2
CANDIDATE_POOL_LIMIT = 20


def rank_candidates(
    candidates: list[ComparisonAlternative],
) -> list[ComparisonAlternative]:
    """Drop zero-coverage stores, sort by (effective_total ASC, distance_km
    ASC), return top MAX_ALTERNATIVES."""
    eligible = [c for c in candidates if c.covered_count > 0]
    eligible.sort(key=lambda c: (c.effective_total, c.distance_km))
    return eligible[:MAX_ALTERNATIVES]


async def find_alternatives(
    session: AsyncSession,
    *,
    source_store_id: int,
    service_id: int,
    cart_items: list[tuple[int, int]],
    customer_latitude: float,
    customer_longitude: float,
    language_code: str,
) -> list[ComparisonAlternative]:
    """Return ranked alternative stores for the given cart.

    1. PostGIS: up to CANDIDATE_POOL_LIMIT nearest serviceable stores
       (excluding the source store) offering `service_id`.
    2. Fetch their inventory rows for the cart's product_ids.
    3. Fetch the source store's current prices for missing-item imputation.
    4. Localize product + store names (English fallback).
    5. Build ComparisonAlternative DTOs; rank via `rank_candidates`.
    """
    if not cart_items:
        return []

    product_ids = [pid for pid, _ in cart_items]

    # --- step 1: PostGIS candidate pool ----------------------------------
    point = "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography"
    sql = text(
        f"SELECT s.id, ST_Distance(a.geo, {point}) / 1000.0 AS distance_km "
        "FROM store s JOIN address a ON a.id = s.address_id "
        "WHERE s.is_active "
        "  AND s.id <> :source_id "
        "  AND a.geo IS NOT NULL "
        f"  AND ST_DWithin(a.geo, {point}, s.delivery_radius_km * 1000) "
        "  AND EXISTS ("
        "    SELECT 1 FROM sellerprofile_service sps "
        "    WHERE sps.seller_profile_id = s.seller_profile_id "
        "      AND sps.service_id = :service_id"
        "  ) "
        f"ORDER BY ST_Distance(a.geo, {point}) ASC "
        "LIMIT :pool_limit"
    )
    rows = (
        await session.exec(  # type: ignore[call-overload]
            sql.bindparams(
                lat=customer_latitude,
                lng=customer_longitude,
                source_id=source_store_id,
                service_id=service_id,
                pool_limit=CANDIDATE_POOL_LIMIT,
            )
        )
    ).all()
    distance_by_store: dict[int, float] = {int(r[0]): float(r[1]) for r in rows}
    candidate_ids = list(distance_by_store.keys())
    if not candidate_ids:
        return []

    # --- step 2: source store's current prices (for imputation) ----------
    src_inv_result = await session.exec(
        select(StoreInventory).where(
            StoreInventory.store_id == source_store_id,
            StoreInventory.product_id.in_(product_ids),  # type: ignore[attr-defined]
        )
    )
    src_price_by_product: dict[int, float] = {
        inv.product_id: inv.price for inv in src_inv_result.all()
    }

    # --- step 3: candidate stores' inventories ---------------------------
    inv_result = await session.exec(
        select(StoreInventory).where(
            StoreInventory.store_id.in_(candidate_ids),  # type: ignore[attr-defined]
            StoreInventory.product_id.in_(product_ids),  # type: ignore[attr-defined]
        )
    )
    inv_by_store: dict[int, dict[int, StoreInventory]] = {}
    for inv in inv_result.all():
        inv_by_store.setdefault(inv.store_id, {})[inv.product_id] = inv

    # --- step 4: localize product + store names --------------------------
    name_result = await session.exec(
        select(MasterProductTranslation).where(
            MasterProductTranslation.master_product_id.in_(product_ids),  # type: ignore[attr-defined]
            MasterProductTranslation.language_code == language_code,
        )
    )
    product_name_by_id: dict[int, str] = {
        row.master_product_id: row.name for row in name_result.all()
    }
    if language_code != "en":
        missing = [pid for pid in product_ids if pid not in product_name_by_id]
        if missing:
            fb_result = await session.exec(
                select(MasterProductTranslation).where(
                    MasterProductTranslation.master_product_id.in_(missing),  # type: ignore[attr-defined]
                    MasterProductTranslation.language_code == "en",
                )
            )
            for row in fb_result.all():
                product_name_by_id.setdefault(row.master_product_id, row.name)

    store_result = await session.exec(
        select(Store).where(Store.id.in_(candidate_ids))  # type: ignore[union-attr]
    )
    store_by_id: dict[int, Store] = {
        s.id: s for s in store_result.all() if s.id is not None
    }

    # --- step 5: build candidate DTOs ------------------------------------
    candidates: list[ComparisonAlternative] = []
    for store_id, store in store_by_id.items():
        store_inv = inv_by_store.get(store_id, {})
        items: list[ComparisonItem] = []
        covered_subtotal = 0.0
        imputed_subtotal = 0.0
        covered_count = 0
        missing_count = 0
        for product_id, quantity in cart_items:
            inv = store_inv.get(product_id)
            available = inv is not None and inv.is_available and inv.stock > 0
            if available and inv is not None:
                unit_price = inv.price
                line_total = unit_price * quantity
                covered_subtotal += line_total
                covered_count += 1
                items.append(ComparisonItem(
                    product_id=product_id,
                    product_name=product_name_by_id.get(product_id, ""),
                    quantity=quantity,
                    inventory_id=inv.id,
                    unit_price=unit_price,
                    is_available=True,
                    stock=inv.stock,
                    line_total=line_total,
                    imputed=False,
                ))
            else:
                src_price = src_price_by_product.get(product_id, 0.0)
                line_total = src_price * quantity
                imputed_subtotal += line_total
                missing_count += 1
                items.append(ComparisonItem(
                    product_id=product_id,
                    product_name=product_name_by_id.get(product_id, ""),
                    quantity=quantity,
                    inventory_id=None,
                    unit_price=src_price,
                    is_available=False,
                    stock=0,
                    line_total=line_total,
                    imputed=True,
                ))
        candidates.append(ComparisonAlternative(
            id=store_id,
            name=store.name,
            distance_km=distance_by_store[store_id],
            covered_count=covered_count,
            missing_count=missing_count,
            covered_subtotal=round(covered_subtotal, 2),
            imputed_subtotal=round(imputed_subtotal, 2),
            effective_total=round(covered_subtotal + imputed_subtotal, 2),
            items=items,
        ))

    return rank_candidates(candidates)
