# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
from sqlalchemy import bindparam, delete, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.catalog import MasterProduct
from app.models.commerce import Favorite
from app.schemas.favorites import (
    FavoriteAtStore,
    FavoriteProductPreview,
    FavoritesGroupedResponse,
    StoreFavGroup,
)


async def add_favorite(
    session: AsyncSession, customer_profile_id: int, product_id: int
) -> None:
    """Idempotent insert. No-op if (customer, product) already exists.

    Raises ValueError("product_not_found") if the master product does not exist.
    """
    exists = await session.get(MasterProduct, product_id)
    if exists is None:
        raise ValueError("product_not_found")

    stmt = pg_insert(Favorite).values(
        customer_profile_id=customer_profile_id,
        product_id=product_id,
    ).on_conflict_do_nothing(
        index_elements=["customer_profile_id", "product_id"],
    )
    await session.execute(stmt)
    await session.commit()


async def remove_favorite(
    session: AsyncSession, customer_profile_id: int, product_id: int
) -> None:
    """Idempotent delete. No-op if no row matches."""
    await session.execute(
        delete(Favorite).where(
            Favorite.customer_profile_id == customer_profile_id,
            Favorite.product_id == product_id,
        )
    )
    await session.commit()


async def list_favorite_ids(
    session: AsyncSession, customer_profile_id: int
) -> list[int]:
    rows = (
        await session.exec(
            select(Favorite.product_id).where(
                Favorite.customer_profile_id == customer_profile_id
            )
        )
    ).all()
    return [int(r) for r in rows]


_GROUPED_SQL = text(
    """
    SELECT f.product_id, f.created_at AS favourited_at,
           COALESCE(mpt.name, mp.slug) AS name,
           mp.image_url,
           sub.category_id,
           i.id AS inventory_id, i.price, i.stock,
           s.id AS store_id, s.name AS store_name,
           ST_Distance(
             s_addr.geo,
             ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
           ) / 1000.0 AS distance_km
    FROM   favorite f
    JOIN   masterproduct mp ON mp.id = f.product_id
    JOIN   subcategory sub ON sub.id = mp.subcategory_id
    LEFT JOIN masterproduct_translation mpt
              ON mpt.master_product_id = mp.id
             AND mpt.language_code = 'en'
    JOIN   storeinventory i ON i.product_id = f.product_id
    JOIN   store s ON s.id = i.store_id
    JOIN   address s_addr ON s_addr.id = s.address_id
    WHERE  f.customer_profile_id = :cid
    AND    s.is_active = true
    AND    ST_DWithin(
             s_addr.geo,
             ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
             s.delivery_radius_km * 1000
           )
    ORDER BY distance_km ASC, f.created_at DESC
    """
)


_UNAVAILABLE_SQL = text(
    """
    SELECT mp.id AS product_id,
           COALESCE(mpt.name, mp.slug) AS name,
           mp.image_url,
           sub.category_id
    FROM   favorite f
    JOIN   masterproduct mp ON mp.id = f.product_id
    JOIN   subcategory sub ON sub.id = mp.subcategory_id
    LEFT JOIN masterproduct_translation mpt
              ON mpt.master_product_id = mp.id
             AND mpt.language_code = 'en'
    WHERE  f.customer_profile_id = :cid
    AND    f.product_id NOT IN :served_ids
    """
).bindparams(bindparam("served_ids", expanding=True))


_ALL_FAV_PRODUCTS_SQL = text(
    """
    SELECT mp.id AS product_id,
           COALESCE(mpt.name, mp.slug) AS name,
           mp.image_url,
           sub.category_id
    FROM   favorite f
    JOIN   masterproduct mp ON mp.id = f.product_id
    JOIN   subcategory sub ON sub.id = mp.subcategory_id
    LEFT JOIN masterproduct_translation mpt
              ON mpt.master_product_id = mp.id
             AND mpt.language_code = 'en'
    WHERE  f.customer_profile_id = :cid
    """
)


async def list_grouped_favorites(
    session: AsyncSession,
    customer_profile_id: int,
    lat: float,
    lng: float,
) -> FavoritesGroupedResponse:
    rows = (
        await session.execute(
            _GROUPED_SQL, {"cid": customer_profile_id, "lat": lat, "lng": lng}
        )
    ).mappings().all()

    groups: dict[int, StoreFavGroup] = {}
    served_ids: set[int] = set()
    for r in rows:
        served_ids.add(int(r["product_id"]))
        sid = int(r["store_id"])
        if sid not in groups:
            groups[sid] = StoreFavGroup(
                store_id=sid,
                store_name=r["store_name"],
                distance_km=float(r["distance_km"]),
                items=[],
            )
        groups[sid].items.append(
            FavoriteAtStore(
                product_id=int(r["product_id"]),
                name=r["name"],
                image_url=r["image_url"],
                category_id=int(r["category_id"]),
                inventory_id=int(r["inventory_id"]),
                price=float(r["price"]),
                stock=int(r["stock"]),
                favourited_at=r["favourited_at"],
            )
        )

    if served_ids:
        unavail_rows = (
            await session.execute(
                _UNAVAILABLE_SQL,
                {"cid": customer_profile_id, "served_ids": list(served_ids)},
            )
        ).mappings().all()
    else:
        unavail_rows = (
            await session.execute(
                _ALL_FAV_PRODUCTS_SQL, {"cid": customer_profile_id}
            )
        ).mappings().all()

    unavailable = [
        FavoriteProductPreview(
            product_id=int(r["product_id"]),
            name=r["name"],
            image_url=r["image_url"],
            category_id=int(r["category_id"]),
        )
        for r in unavail_rows
    ]
    return FavoritesGroupedResponse(groups=list(groups.values()), unavailable=unavailable)


_STORE_FAV_SQL = text(
    """
    SELECT f.product_id, f.created_at AS favourited_at,
           COALESCE(mpt.name, mp.slug) AS name,
           mp.image_url,
           sub.category_id,
           i.id AS inventory_id, i.price, i.stock
    FROM   favorite f
    JOIN   masterproduct mp ON mp.id = f.product_id
    JOIN   subcategory sub ON sub.id = mp.subcategory_id
    LEFT JOIN masterproduct_translation mpt
              ON mpt.master_product_id = mp.id
             AND mpt.language_code = 'en'
    JOIN   storeinventory i ON i.product_id = f.product_id
    WHERE  f.customer_profile_id = :cid
    AND    i.store_id = :sid
    ORDER BY f.created_at DESC
    """
)


async def list_store_favorites(
    session: AsyncSession,
    customer_profile_id: int,
    store_id: int,
) -> list[FavoriteAtStore]:
    rows = (
        await session.execute(
            _STORE_FAV_SQL, {"cid": customer_profile_id, "sid": store_id}
        )
    ).mappings().all()
    return [
        FavoriteAtStore(
            product_id=int(r["product_id"]),
            name=r["name"],
            image_url=r["image_url"],
            category_id=int(r["category_id"]),
            inventory_id=int(r["inventory_id"]),
            price=float(r["price"]),
            stock=int(r["stock"]),
            favourited_at=r["favourited_at"],
        )
        for r in rows
    ]
