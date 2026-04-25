#!/usr/bin/env python3
"""
Seed only the seller-review subset as a compatibility/helper entrypoint.

This is not the canonical full dev seed path. It only creates the admin review
accounts used for the seller application workflow walkthrough.

Usage (from backend/app/):
    uv run python scripts/seed_seller_applications.py
"""

import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.core.config import settings
from app.db.dev_seed import (
    get_seller_application_subset_login_email_rows,
    seed_seller_application_subset,
)


async def main() -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    try:
        async with AsyncSession(engine) as session:
            await seed_seller_application_subset(session)
            await session.commit()
    finally:
        await engine.dispose()

    print("Seeded seller review subset login emails:")
    print("  note: this helper does not seed the canonical full dev dataset.")
    for role, email in get_seller_application_subset_login_email_rows():
        print(f"  {role}: {email}")


if __name__ == "__main__":
    asyncio.run(main())
