#!/usr/bin/env python3
"""
Seed seller application records for the approval workflow walkthrough.

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
from app.db.dev_seed import ADMIN, APPLICATIONS, seed_seller_application_subset


async def main() -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    try:
        async with AsyncSession(engine) as session:
            await seed_seller_application_subset(session)
            await session.commit()
    finally:
        await engine.dispose()

    print("Seeded seller application login emails:")
    print(f"  admin: {ADMIN['email']}")
    for application in APPLICATIONS:
        print(f"  seller: {application['email']}")


if __name__ == "__main__":
    asyncio.run(main())
