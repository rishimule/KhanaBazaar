#!/usr/bin/env bash
# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
#
# Docker-free local infrastructure: Postgres 15 + PostGIS 3.4, Redis 7, Meilisearch v1.11.
#
# Everything installs into $KB_HOME (default ~/.local/share/khanabazaar) with no
# root and no system packages. Postgres/Redis/Node come from conda-forge via
# micromamba; Meilisearch is the upstream static binary.
#
# Two ways to use this file:
#   ./scripts/native_infra.sh setup        # one-time install + initdb
#   source scripts/native_infra.sh         # paths + infra_native_* functions (dev.sh does this)
#
# Service state is machine-global (like the old Docker named volumes) because the
# ports are: two checkouts cannot both own :5432. Per-checkout app pids stay in .dev/.
set -euo pipefail

# Versions mirror docker-compose.yml. The conda solver pairs PostGIS 3.4 with
# Postgres 15 on its own, matching the postgis/postgis:15-3.4 image.
KB_PG_MAJOR="${KB_PG_MAJOR:-15}"
KB_REDIS_VERSION="${KB_REDIS_VERSION:-7.4}"
KB_NODE_VERSION="${KB_NODE_VERSION:-22}"
KB_MEILI_VERSION="${KB_MEILI_VERSION:-v1.11.3}"

KB_HOME="${KB_HOME:-$HOME/.local/share/khanabazaar}"
KB_BIN="${KB_HOME}/bin"
KB_DATA="${KB_HOME}/data"
KB_RUN="${KB_HOME}/run"
KB_INFRA_LOG_DIR="${KB_HOME}/logs"

KB_MAMBA_BIN="${KB_BIN}/micromamba"
KB_MAMBA_ROOT="${KB_HOME}/mamba"
KB_ENV="${KB_MAMBA_ROOT}/envs/kb-dev"
KB_ENV_BIN="${KB_ENV}/bin"
KB_MEILI_BIN="${KB_BIN}/meilisearch"

KB_PGDATA="${KB_DATA}/pgdata"
KB_REDIS_DATA="${KB_DATA}/redis"
KB_MEILI_DATA="${KB_DATA}/meili"
KB_MEILI_TEST_DATA="${KB_DATA}/meili-test"

KB_REDIS_PID="${KB_RUN}/redis.pid"
KB_MEILI_PID="${KB_RUN}/meili.pid"
KB_MEILI_TEST_PID="${KB_RUN}/meili-test.pid"

KB_MEILI_PORT=7700
KB_MEILI_TEST_PORT=7701

# Mirrors docker-compose.yml's ${MEILI_MASTER_KEY:-dev-master-key-change-me}.
KB_MEILI_MASTER_KEY="${MEILI_MASTER_KEY:-dev-master-key-change-me}"
KB_MEILI_TEST_KEY="${MEILI_TEST_KEY:-test-master-key}"

KB_DEV_DB="khanabazaar"
KB_TEST_DB="khanabazaar_test"

# ---------------------------------------------------------------- tiny helpers

_kb_pid_alive() {
  local pid_file="$1"
  [ -f "${pid_file}" ] && kill -0 "$(cat "${pid_file}")" 2>/dev/null
}

# Liveness probes. These -- not the pid files -- decide whether a service is
# already up. setsid forks when it is already a process-group leader, in which
# case the recorded $! is a wrapper that exits immediately and the pid file goes
# stale while the daemon keeps running. Probing the port avoids that trap.
_kb_probe_redis()      { "${KB_ENV_BIN}/redis-cli" -p 6379 ping >/dev/null 2>&1; }
_kb_probe_meili()      { curl -fsS --max-time 1 "http://localhost:${KB_MEILI_PORT}/health" >/dev/null 2>&1; }
_kb_probe_meili_test() { curl -fsS --max-time 1 "http://localhost:${KB_MEILI_TEST_PORT}/health" >/dev/null 2>&1; }
_kb_probe_pg()         { "${KB_ENV_BIN}/pg_ctl" -D "${KB_PGDATA}" status >/dev/null 2>&1; }

_kb_start_daemon() {
  # _kb_start_daemon <name> <pid_file> <log_file> <probe_fn> <cmd...>
  local name="$1" pid_file="$2" log_file="$3" probe="$4"
  shift 4
  if "${probe}"; then
    echo "  ${name} already running"
    return 0
  fi
  mkdir -p "$(dirname "${pid_file}")" "$(dirname "${log_file}")"
  # The subshell keeps setsid from being a process-group leader, so it execs
  # instead of forking and $! is the real daemon pid (same trick as dev.sh).
  (
    setsid nohup "$@" >"${log_file}" 2>&1 < /dev/null &
    echo $! >"${pid_file}"
  )
  local attempt
  for attempt in $(seq 1 60); do
    if "${probe}"; then
      echo "  ${name} started (pid $(cat "${pid_file}" 2>/dev/null || echo '?'))"
      return 0
    fi
    sleep 0.5
  done
  echo "  ${name} failed to start. Tail of ${log_file}:" >&2
  tail -n 20 "${log_file}" >&2 || true
  return 1
}

_kb_stop_daemon() {
  # _kb_stop_daemon <name> <pid_file> <probe_fn> [pkill_pattern]
  local name="$1" pid_file="$2" probe="$3" pattern="${4:-}"
  if ! "${probe}"; then
    rm -f "${pid_file}"
    echo "  ${name} not running"
    return 0
  fi
  if _kb_pid_alive "${pid_file}"; then
    local pid
    pid="$(cat "${pid_file}")"
    kill -- -"${pid}" 2>/dev/null || kill "${pid}" 2>/dev/null || true
    for _ in $(seq 1 20); do
      "${probe}" || break
      sleep 0.25
    done
    kill -0 "${pid}" 2>/dev/null && { kill -9 -- -"${pid}" 2>/dev/null || kill -9 "${pid}" 2>/dev/null || true; }
  fi
  # Stale pid file but the port still answers: fall back to matching the exact
  # binary path, which is unique to this install.
  if "${probe}" && [ -n "${pattern}" ]; then
    pkill -f "${pattern}" 2>/dev/null || true
    for _ in $(seq 1 20); do
      "${probe}" || break
      sleep 0.25
    done
  fi
  rm -f "${pid_file}"
  if "${probe}"; then
    echo "  ${name} still responding -- stop it manually" >&2
    return 1
  fi
  echo "  ${name} stopped"
}

_kb_psql() {
  # Always over TCP: that is the path asyncpg takes from the app.
  PGPASSWORD=password "${KB_ENV_BIN}/psql" -h 127.0.0.1 -p 5432 -U postgres -v ON_ERROR_STOP=1 "$@"
}

infra_native_installed() {
  [ -x "${KB_ENV_BIN}/postgres" ] && [ -x "${KB_ENV_BIN}/redis-server" ] && [ -x "${KB_MEILI_BIN}" ]
}

# ---------------------------------------------------------------------- install

infra_native_setup() {
  mkdir -p "${KB_BIN}" "${KB_DATA}" "${KB_RUN}" "${KB_INFRA_LOG_DIR}"

  if [ ! -x "${KB_MAMBA_BIN}" ]; then
    echo "Installing micromamba..."
    curl -Ls --max-time 300 https://micro.mamba.pm/api/micromamba/linux-64/latest \
      | tar -xj -C "${KB_HOME}" bin/micromamba
  fi
  echo "micromamba: $("${KB_MAMBA_BIN}" --version)"

  # Re-running this is safe, but the spec list must stay complete: micromamba
  # 'create' on an existing prefix PRUNES anything not named here, so dropping a
  # package from this call silently uninstalls it.
  echo "Creating conda env 'kb-dev' (postgres ${KB_PG_MAJOR} + postgis, redis ${KB_REDIS_VERSION}, node ${KB_NODE_VERSION})..."
  MAMBA_ROOT_PREFIX="${KB_MAMBA_ROOT}" "${KB_MAMBA_BIN}" create -n kb-dev -y -c conda-forge \
    "postgresql=${KB_PG_MAJOR}" postgis \
    "redis-server=${KB_REDIS_VERSION}" \
    "nodejs=${KB_NODE_VERSION}"

  if [ ! -x "${KB_MEILI_BIN}" ]; then
    echo "Downloading Meilisearch ${KB_MEILI_VERSION}..."
    curl -L --max-time 900 --retry 2 -o "${KB_MEILI_BIN}.tmp" \
      "https://github.com/meilisearch/meilisearch/releases/download/${KB_MEILI_VERSION}/meilisearch-linux-amd64"
    chmod +x "${KB_MEILI_BIN}.tmp"
    mv "${KB_MEILI_BIN}.tmp" "${KB_MEILI_BIN}"
  fi

  if ! command -v uv >/dev/null 2>&1 && [ ! -x "${HOME}/.local/bin/uv" ]; then
    echo "Installing uv..."
    curl -LsSf --max-time 300 https://astral.sh/uv/install.sh \
      | env UV_INSTALL_DIR="${HOME}/.local/bin" sh
  fi

  infra_native_initdb
  infra_native_up
  infra_native_create_databases

  cat <<EOF

Native infra ready.
  Postgres:    localhost:5432   (user postgres / password password)
  Redis:       localhost:6379
  Meilisearch: http://localhost:${KB_MEILI_PORT}

Binaries live in ${KB_ENV_BIN} and ${KB_BIN}; data in ${KB_DATA}.
'./scripts/dev.sh' picks this up automatically -- no PATH changes needed.
EOF
}

infra_native_initdb() {
  if [ -f "${KB_PGDATA}/PG_VERSION" ]; then
    echo "Postgres cluster already initialized (PG $(cat "${KB_PGDATA}/PG_VERSION"))"
    return 0
  fi
  echo "Initializing Postgres cluster at ${KB_PGDATA}..."
  "${KB_ENV_BIN}/initdb" -D "${KB_PGDATA}" -U postgres \
    --auth-local=trust --auth-host=trust --encoding=UTF8 >/dev/null

  # Local-only listener on the port the app's DATABASE_URL expects, plus a
  # writable socket dir (the conda default points outside $HOME).
  cat >> "${KB_PGDATA}/postgresql.conf" <<EOF

# --- khanabazaar dev (managed by scripts/native_infra.sh) ---
listen_addresses = 'localhost'
port = 5432
unix_socket_directories = '${KB_RUN}'
EOF
}

infra_native_create_databases() {
  # Keep the password path working too, not just --auth-host=trust, so the
  # DATABASE_URL from .env.example is accurate.
  _kb_psql -d postgres -tAc "ALTER USER postgres WITH PASSWORD 'password';" >/dev/null
  local db
  for db in "${KB_DEV_DB}" "${KB_TEST_DB}"; do
    if ! _kb_psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${db}'" | grep -q 1; then
      _kb_psql -d postgres -tAc "CREATE DATABASE ${db} OWNER postgres;" >/dev/null
      echo "  created database ${db}"
    fi
    # Alembic creates these too, but the test harness drops/recreates tables
    # without re-running migrations, so both DBs need the extensions present.
    _kb_psql -d "${db}" -tAc \
      "CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS pg_trgm;" >/dev/null
  done
  echo "  postgis: $(_kb_psql -d "${KB_DEV_DB}" -tAc 'SELECT postgis_version();')"
}

# ------------------------------------------------------------ lifecycle: up/down

infra_native_up() {
  local with_test="${1:-0}"

  if _kb_probe_pg; then
    echo "  postgres already running"
  else
    "${KB_ENV_BIN}/pg_ctl" -D "${KB_PGDATA}" -l "${KB_INFRA_LOG_DIR}/postgres.log" -w start >/dev/null
    echo "  postgres started"
  fi

  _kb_start_daemon "redis" "${KB_REDIS_PID}" "${KB_INFRA_LOG_DIR}/redis.log" _kb_probe_redis \
    "${KB_ENV_BIN}/redis-server" --port 6379 --dir "${KB_REDIS_DATA}" \
    --daemonize no --save 60 1 --appendonly no

  mkdir -p "${KB_MEILI_DATA}"
  _kb_start_daemon "meilisearch" "${KB_MEILI_PID}" "${KB_INFRA_LOG_DIR}/meilisearch.log" _kb_probe_meili \
    env MEILI_MASTER_KEY="${KB_MEILI_MASTER_KEY}" MEILI_ENV=development MEILI_NO_ANALYTICS=true \
        "${KB_MEILI_BIN}" --http-addr "localhost:${KB_MEILI_PORT}" --db-path "${KB_MEILI_DATA}"

  if [ "${with_test}" = "1" ]; then
    mkdir -p "${KB_MEILI_TEST_DATA}"
    _kb_start_daemon "meilisearch-test" "${KB_MEILI_TEST_PID}" "${KB_INFRA_LOG_DIR}/meilisearch-test.log" _kb_probe_meili_test \
      env MEILI_MASTER_KEY="${KB_MEILI_TEST_KEY}" MEILI_ENV=development MEILI_NO_ANALYTICS=true \
          "${KB_MEILI_BIN}" --http-addr "localhost:${KB_MEILI_TEST_PORT}" --db-path "${KB_MEILI_TEST_DATA}"
  fi
}

infra_native_down() {
  _kb_stop_daemon "meilisearch-test" "${KB_MEILI_TEST_PID}" _kb_probe_meili_test \
    "${KB_MEILI_BIN} --http-addr localhost:${KB_MEILI_TEST_PORT}"
  _kb_stop_daemon "meilisearch" "${KB_MEILI_PID}" _kb_probe_meili \
    "${KB_MEILI_BIN} --http-addr localhost:${KB_MEILI_PORT}"
  _kb_stop_daemon "redis" "${KB_REDIS_PID}" _kb_probe_redis "${KB_ENV_BIN}/redis-server"
  mkdir -p "${KB_RUN}"
  if _kb_probe_pg; then
    "${KB_ENV_BIN}/pg_ctl" -D "${KB_PGDATA}" -m fast -w stop >/dev/null
    echo "  postgres stopped"
  else
    echo "  postgres not running"
  fi
}

infra_native_wait_ready() {
  local attempt
  for attempt in $(seq 1 60); do
    _kb_psql -d "${KB_DEV_DB}" -tAc 'SELECT 1' >/dev/null 2>&1 && break
    [ "${attempt}" -eq 60 ] && { echo "Postgres did not accept TCP queries" >&2; return 1; }
    sleep 1
  done
  for attempt in $(seq 1 60); do
    _kb_probe_redis && break
    [ "${attempt}" -eq 60 ] && { echo "Redis did not become ready" >&2; return 1; }
    sleep 1
  done
  for attempt in $(seq 1 60); do
    _kb_probe_meili && break
    [ "${attempt}" -eq 60 ] && { echo "Meilisearch did not become ready" >&2; return 1; }
    sleep 1
  done
}

infra_native_status() {
  if _kb_probe_pg; then
    echo "  postgres:        running (localhost:5432)"
  else
    echo "  postgres:        stopped"
  fi
  if _kb_probe_redis; then
    echo "  redis:           running (localhost:6379)"
  else
    echo "  redis:           stopped"
  fi
  if _kb_probe_meili; then
    echo "  meilisearch:     running (http://localhost:${KB_MEILI_PORT})"
  else
    echo "  meilisearch:     stopped"
  fi
  if _kb_probe_meili_test; then
    echo "  meilisearch-test: running (http://localhost:${KB_MEILI_TEST_PORT})"
  fi
  echo "  logs:            ${KB_INFRA_LOG_DIR}"
}

infra_native_reset() {
  # Destroys all local Postgres / Redis / Meilisearch state, then rebuilds
  # empty clusters. Callers re-apply migrations + reseed afterwards.
  infra_native_down
  echo "Wiping ${KB_DATA}..."
  rm -rf "${KB_PGDATA}" "${KB_REDIS_DATA}" "${KB_MEILI_DATA}" "${KB_MEILI_TEST_DATA}"
  mkdir -p "${KB_DATA}"
  infra_native_initdb
  infra_native_up
  infra_native_wait_ready
  infra_native_create_databases
}

# ------------------------------------------------------------------ direct entry

# Only dispatch when executed, not when sourced.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  case "${1:-}" in
    setup)     infra_native_setup ;;
    up)
      shift
      _with_test=0
      case "${1:-}" in
        --with-test) _with_test=1 ;;
        "") ;;
        *) echo "Unknown up arg: $1 (expected --with-test)" >&2; exit 1 ;;
      esac
      infra_native_up "${_with_test}"
      infra_native_wait_ready
      ;;
    down)      infra_native_down ;;
    status)    infra_native_status ;;
    reset)     infra_native_reset ;;
    databases) infra_native_create_databases ;;
    *)
      cat <<EOF
Usage: $0 <setup|up|down|status|reset|databases>

  setup       One-time install (micromamba env, Meilisearch, uv) + initdb + databases
  up          Start postgres + redis + meilisearch
  up --with-test
              Also start meilisearch-test on :${KB_MEILI_TEST_PORT} (needed by 'uv run pytest')
  down        Stop all three (and meilisearch-test)
  status      Show what is running
  reset       Destroy all data and rebuild empty clusters
  databases   Ensure khanabazaar + khanabazaar_test exist with postgis/pg_trgm
EOF
      exit 1 ;;
  esac
fi
