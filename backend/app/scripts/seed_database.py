#!/usr/bin/env python3
"""
Seed the local database with canonical dev data.

Usage (from backend/app/):
    uv run python scripts/seed_database.py [--verify-only]
"""

import argparse
import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.core.config import settings
from app.db.dev_seed import TEST_USERS, seed_demo_data, verify_expected_counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed canonical dev data")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Skip seeding and verify the current database matches expected counts",
    )
    return parser.parse_args()


def print_counts(counts: dict[str, int]) -> None:
    print("Verified counts:")
    for key, value in counts.items():
        print(f"  {key}: {value}")


def print_seeded_emails() -> None:
    print("\nSeeded login emails:")
    for user in TEST_USERS:
        print(f"  {user['role'].value}: {user['email']}")


async def main() -> None:
    args = parse_args()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    try:
        async with AsyncSession(engine) as session:
            if not args.verify_only:
                await seed_demo_data(session)
                await session.commit()

            counts = await verify_expected_counts(session)
            print_counts(counts)

            if not args.verify_only:
                print_seeded_emails()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
