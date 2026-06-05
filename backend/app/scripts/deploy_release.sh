#!/usr/bin/env bash
# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# Run by the kb-migrate Cloud Run Job on every deploy.
set -euo pipefail

echo "==> alembic upgrade head"
alembic upgrade head

echo "==> seed (skips if catalog already populated)"
python scripts/seed_database.py --skip-if-seeded --no-reindex

echo "==> reindex Meilisearch (idempotent, keeps search in sync with catalog)"
python -m app.search.reindex --all

echo "==> release tasks complete"
