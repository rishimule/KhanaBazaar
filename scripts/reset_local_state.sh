#!/usr/bin/env bash
# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_APP_DIR="${REPO_ROOT}/backend/app"

require_command() {
  local command_name="$1"

  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Missing required command: ${command_name}" >&2
    exit 1
  fi
}

require_command docker
require_command uv

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose is not available" >&2
  exit 1
fi

if [ ! -f "${REPO_ROOT}/docker-compose.yml" ]; then
  echo "Expected docker-compose.yml at repo root: ${REPO_ROOT}" >&2
  exit 1
fi

if [ ! -d "${BACKEND_APP_DIR}" ]; then
  echo "Expected backend app directory at: ${BACKEND_APP_DIR}" >&2
  exit 1
fi

if [ ! -f "${BACKEND_APP_DIR}/.env" ]; then
  echo "Expected backend env file at: ${BACKEND_APP_DIR}/.env" >&2
  exit 1
fi

(
  cd "${BACKEND_APP_DIR}"
  uv run python - <<'PY'
import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "src"))

from app.core.config import settings
from app.db.local_reset import validate_local_connection_urls

validate_local_connection_urls(settings.DATABASE_URL, settings.REDIS_URL)
PY
)

cd "${REPO_ROOT}"
docker compose down -v

for container_name in khanabazaar-postgres khanabazaar-redis; do
  if docker container inspect "${container_name}" >/dev/null 2>&1; then
    docker rm -f "${container_name}" >/dev/null
  fi
done

docker compose up -d postgres redis

for attempt in $(seq 1 60); do
  if docker compose exec -T postgres pg_isready -U postgres -d khanabazaar >/dev/null 2>&1; then
    break
  fi

  if [ "${attempt}" -eq 60 ]; then
    echo "Postgres did not become ready in time" >&2
    exit 1
  fi

  sleep 1
done

(
  cd "${BACKEND_APP_DIR}"
  uv run alembic upgrade head
  uv run python scripts/seed_database.py
  uv run python scripts/seed_database.py --verify-only
)

echo "Local state reset complete."
