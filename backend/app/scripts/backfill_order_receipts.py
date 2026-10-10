# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Idempotent backfill: issue receipts for every delivered order that has
none, oldest delivery first, with no emails (spec 2026-10-10 §7). Wired into
scripts/deploy_release.sh right after `alembic upgrade head`, so history is
numbered before the new API issues its first live receipt.

Exits non-zero when any order fails, so the kb-migrate job stops the deploy
before the new API goes live: shipping anyway would let live receipts take
numbers ahead of the history the failed orders belong to."""
import asyncio
import sys

from app.db.session import async_session_factory
from app.services.receipts import issue_missing


async def _main() -> int:
    async with async_session_factory() as session:
        result = await issue_missing(session)
    print(
        f"backfill_order_receipts: issued {result.issued} receipt(s), "
        f"{result.failed} failed"
    )
    return 1 if result.failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
