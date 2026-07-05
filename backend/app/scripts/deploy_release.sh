#!/usr/bin/env bash
# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# Run by the kb-migrate Cloud Run Job on every deploy.
set -euo pipefail

# Ensure PostGIS exists before migrations (the geo generated column + GiST index
# depend on it). Runs in-VPC via the Cloud SQL connector — reliable, unlike a
# laptop-side `gcloud sql connect`. kbuser has cloudsqlsuperuser, which Cloud SQL
# permits to create the postgis extension. Idempotent.
echo "==> ensure PostGIS extension"
python - <<'PY'
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings


async def main() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    finally:
        await engine.dispose()


asyncio.run(main())
PY

echo "==> alembic upgrade head"
alembic upgrade head

echo "==> backfill freebie fee arrangements (idempotent)"
python scripts/backfill_freebie_arrangements.py

echo "==> seed policy documents (idempotent; inserts v1 only if absent)"
python -m app.db.seed_policies

echo "==> seed (skips if catalog already populated)"
python scripts/seed_database.py --skip-if-seeded --no-reindex

echo "==> reindex Meilisearch (idempotent, keeps search in sync with catalog)"
python -m app.search.reindex --all

echo "==> release tasks complete"
