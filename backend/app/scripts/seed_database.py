#!/usr/bin/env python3
# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
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
from app.db.dev_seed import (
    get_canonical_login_email_rows,
    seed_demo_data,
    verify_expected_counts,
)
from app.search.client import get_meili_client
from app.search.reindex import reindex_all


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed canonical dev data")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Skip seeding and verify the current database matches expected counts",
    )
    parser.add_argument(
        "--no-reindex",
        action="store_true",
        help="Skip the post-seed Meilisearch reindex step",
    )
    return parser.parse_args()


def print_counts(counts: dict[str, int]) -> None:
    print("Verified counts:")
    for key, value in counts.items():
        print(f"  {key}: {value}")


def print_seeded_emails() -> None:
    print("\nSeeded login emails:")
    for role, email in get_canonical_login_email_rows():
        print(f"  {role}: {email}")


async def _reindex_meilisearch(session: AsyncSession) -> None:
    # Bulk seeding inserts rows in raw SQL paths that don't always trigger the
    # SQLAlchemy after_commit hooks search.hooks relies on, so the Meilisearch
    # indexes drift from the freshly-seeded catalog. Push everything once at
    # the end so /api/v1/search/* matches the new data.
    client = get_meili_client()
    counts = await reindex_all(session, client)
    print("\nReindexed Meilisearch:")
    for key, value in counts.items():
        print(f"  {key}: {value}")


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
                if not args.no_reindex:
                    await _reindex_meilisearch(session)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
