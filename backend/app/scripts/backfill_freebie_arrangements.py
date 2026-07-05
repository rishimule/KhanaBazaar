# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Idempotent one-off backfill: enroll every existing store's offered services
into a Freebie Trial arrangement. Safe to run repeatedly (sync skips existing).
Wired into scripts/deploy_release.sh after `alembic upgrade head`."""
import asyncio

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.session import async_session_factory
from app.models.store import Store
from app.services.fee_lifecycle import sync_store_arrangements


async def backfill_all(session: AsyncSession) -> int:
    profile_ids = (await session.exec(select(Store.seller_profile_id))).all()
    for pid in profile_ids:
        await sync_store_arrangements(session, pid)
    return len(profile_ids)


async def _main() -> None:
    async with async_session_factory() as session:
        n = await backfill_all(session)
        await session.commit()
    print(f"backfill_freebie_arrangements: processed {n} store(s)")


if __name__ == "__main__":
    asyncio.run(_main())
