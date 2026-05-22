#!/usr/bin/env bash
# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_APP_DIR="${REPO_ROOT}/backend/app"
FRONTEND_DIR="${REPO_ROOT}/frontend"
RUN_DIR="${REPO_ROOT}/.dev"
LOG_DIR="${RUN_DIR}/logs"

BACKEND_PID="${RUN_DIR}/backend.pid"
CELERY_PID="${RUN_DIR}/celery.pid"
FRONTEND_PID="${RUN_DIR}/frontend.pid"
LOG_VIEWER_PID="${RUN_DIR}/log_viewer.pid"

BACKEND_LOG="${LOG_DIR}/backend.log"
CELERY_LOG="${LOG_DIR}/celery.log"
FRONTEND_LOG="${LOG_DIR}/frontend.log"
LOG_VIEWER_LOG="${LOG_DIR}/log_viewer.log"

NGROK_PID="${RUN_DIR}/ngrok.pid"
NGROK_LOG="${LOG_DIR}/ngrok.log"
NGROK_API="http://localhost:4040/api/tunnels"
export LOG_VIEWER_PORT="${LOG_VIEWER_PORT:-8001}"

mkdir -p "${RUN_DIR}" "${LOG_DIR}"

require_command() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Missing required command: ${cmd}" >&2
    exit 1
  fi
}

is_running() {
  local pid_file="$1"
  [ -f "${pid_file}" ] && kill -0 "$(cat "${pid_file}")" 2>/dev/null
}

start_proc() {
  local name="$1" pid_file="$2" log_file="$3" workdir="$4"
  shift 4

  if is_running "${pid_file}"; then
    echo "${name} already running (pid $(cat "${pid_file}"))"
    return 0
  fi

  echo "Starting ${name}..."
  # setsid puts the child in a new process group so stop_proc can kill the
  # whole group (PGID == leader PID). Avoids orphaned grandchildren like
  # next-server that reparent to init when their parent shell exits.
  (
    cd "${workdir}"
    setsid nohup "$@" >"${log_file}" 2>&1 < /dev/null &
    echo $! >"${pid_file}"
  )
  sleep 0.3
  if is_running "${pid_file}"; then
    echo "${name} started (pid $(cat "${pid_file}")) -> ${log_file}"
  else
    echo "${name} failed to start. Tail of log:" >&2
    tail -n 30 "${log_file}" >&2 || true
    return 1
  fi
}

stop_proc() {
  local name="$1" pid_file="$2"
  if ! is_running "${pid_file}"; then
    echo "${name} not running"
    rm -f "${pid_file}"
    return 0
  fi
  local pid
  pid="$(cat "${pid_file}")"
  echo "Stopping ${name} (pid ${pid})..."
  # Kill the whole process group (started via setsid). Falls back to single
  # PID if PGID kill fails (e.g. older PID file from before setsid was used).
  kill -- -"${pid}" 2>/dev/null || kill "${pid}" 2>/dev/null || true
  for _ in $(seq 1 20); do
    kill -0 "${pid}" 2>/dev/null || break
    sleep 0.25
  done
  if kill -0 "${pid}" 2>/dev/null; then
    echo "Force killing ${name}..."
    kill -9 -- -"${pid}" 2>/dev/null || kill -9 "${pid}" 2>/dev/null || true
  fi
  rm -f "${pid_file}"
}

status_proc() {
  local name="$1" pid_file="$2"
  if is_running "${pid_file}"; then
    echo "  ${name}: running (pid $(cat "${pid_file}"))"
  else
    echo "  ${name}: stopped"
  fi
}

print_tunnels() {
  # One-shot listing of every active ngrok tunnel. Prints indented lines:
  # "    <name> (<proto>): <public_url>  ->  <addr>". Returns 1 if no tunnels.
  local data
  data="$(curl -s --max-time 1 "${NGROK_API}" 2>/dev/null)" || return 1
  [ -z "${data}" ] && return 1
  echo "${data}" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)
tunnels = data.get("tunnels") or []
if not tunnels:
    sys.exit(1)
for t in tunnels:
    name = t.get("name", "?")
    proto = t.get("proto", "?")
    public = t.get("public_url", "?")
    addr = (t.get("config") or {}).get("addr", "?")
    print(f"      {name} ({proto}): {public}  ->  {addr}")
' || return 1
}

fetch_tunnel_url() {
  # Polls ngrok's local agent API for up to ~10s and prints the public URL
  # for the named tunnel on stdout. Defaults to the first tunnel if no name
  # is provided. Returns 0 if a URL is found, 1 otherwise.
  local want="${1:-}" attempt url
  for attempt in $(seq 1 20); do
    url="$(curl -s --max-time 1 "${NGROK_API}" 2>/dev/null \
      | TUNNEL_NAME="${want}" python3 -c '
import json, os, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
want = os.environ.get("TUNNEL_NAME") or ""
tunnels = data.get("tunnels") or []
if not tunnels:
    sys.exit(0)
if want:
    for t in tunnels:
        if t.get("name") == want and t.get("proto") == "https":
            print(t.get("public_url", ""))
            sys.exit(0)
    for t in tunnels:
        if t.get("name") == want:
            print(t.get("public_url", ""))
            sys.exit(0)
else:
    for t in tunnels:
        if t.get("proto") == "https":
            print(t.get("public_url", ""))
            sys.exit(0)
    print(tunnels[0].get("public_url", ""))
' 2>/dev/null)"
    if [ -n "${url}" ]; then
      echo "${url}"
      return 0
    fi
    sleep 0.5
  done
  return 1
}

cmd_tunnel() {
  require_command ngrok
  require_command curl
  require_command python3

  if ! is_running "${LOG_VIEWER_PID}"; then
    start_proc "log_viewer" "${LOG_VIEWER_PID}" "${LOG_VIEWER_LOG}" "${REPO_ROOT}" \
      python3 "${SCRIPT_DIR}/log_viewer.py"
  fi

  start_proc "ngrok"   "${NGROK_PID}"   "${NGROK_LOG}"   "${REPO_ROOT}" \
    ngrok http 3000 --log=stdout --log-format=logfmt \
      --traffic-policy-file "${SCRIPT_DIR}/ngrok-traffic-policy.yml"

  echo -n "Resolving tunnel URL"
  local url
  if url="$(fetch_tunnel_url)"; then
    echo
    echo "Tunnel ready: ${url}  ->  :3000  (frontend; logs at ${url}/dev-logs/)"
  else
    echo
    echo "Tunnel started but URL unresolved. See ${NGROK_LOG}." >&2
  fi
}

cmd_tunnel_url() {
  if ! is_running "${NGROK_PID}"; then
    echo "ngrok not running" >&2
    exit 1
  fi
  local url
  if url="$(fetch_tunnel_url)"; then
    echo "${url}"
  else
    echo "ngrok running but URL not yet available; check ${NGROK_LOG}" >&2
    exit 1
  fi
}

cmd_start() {
  local with_tunnel=0
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --tunnel) with_tunnel=1; shift ;;
      *) echo "Unknown start arg: $1" >&2; exit 1 ;;
    esac
  done

  require_command docker
  require_command uv
  require_command npm

  if ! docker compose version >/dev/null 2>&1; then
    echo "docker compose not available" >&2
    exit 1
  fi

  echo "Bringing up Postgres + Redis + Meilisearch..."
  (cd "${REPO_ROOT}" && docker compose up -d postgres redis meilisearch)

  for attempt in $(seq 1 60); do
    if (cd "${REPO_ROOT}" && docker compose exec -T postgres pg_isready -U postgres -d khanabazaar >/dev/null 2>&1); then
      break
    fi
    [ "${attempt}" -eq 60 ] && { echo "Postgres did not become ready" >&2; exit 1; }
    sleep 1
  done

  for attempt in $(seq 1 60); do
    if curl -fsS --max-time 1 http://localhost:7700/health >/dev/null 2>&1; then
      break
    fi
    [ "${attempt}" -eq 60 ] && { echo "Meilisearch did not become ready" >&2; exit 1; }
    sleep 1
  done

  start_proc "backend"  "${BACKEND_PID}"  "${BACKEND_LOG}"  "${BACKEND_APP_DIR}" \
    uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

  start_proc "celery"   "${CELERY_PID}"   "${CELERY_LOG}"   "${BACKEND_APP_DIR}" \
    uv run celery -A app.core.celery_app worker --loglevel=info

  start_proc "frontend" "${FRONTEND_PID}" "${FRONTEND_LOG}" "${FRONTEND_DIR}" \
    npm run dev

  start_proc "log_viewer" "${LOG_VIEWER_PID}" "${LOG_VIEWER_LOG}" "${REPO_ROOT}" \
    python3 "${SCRIPT_DIR}/log_viewer.py"

  if [ "${with_tunnel}" -eq 1 ]; then
    cmd_tunnel
  fi

  echo
  echo "All services up."
  echo "  Backend:     http://localhost:8000  (docs: /docs)"
  echo "  Frontend:    http://localhost:3000"
  echo "  Meilisearch: http://localhost:7700"
  echo "  Log viewer:  http://localhost:${LOG_VIEWER_PORT}"
  if [ "${with_tunnel}" -eq 1 ] && is_running "${NGROK_PID}"; then
    local url
    if url="$(fetch_tunnel_url)"; then
      echo "  Tunnel:     ${url}  ->  :3000"
      echo "  Tunnel Log: ${url}/dev-logs/  (proxied through frontend)"
    fi
  fi
  echo "  Logs:       ${LOG_DIR}"
  echo "Run '${0} logs [backend|celery|frontend|ngrok|log_viewer]' to tail logs."
}

cmd_stop() {
  stop_proc "ngrok"      "${NGROK_PID}"
  stop_proc "log_viewer" "${LOG_VIEWER_PID}"
  stop_proc "frontend"   "${FRONTEND_PID}"
  stop_proc "celery"     "${CELERY_PID}"
  stop_proc "backend"    "${BACKEND_PID}"

  if [ "${1:-}" = "--all" ]; then
    echo "Stopping Docker services..."
    (cd "${REPO_ROOT}" && docker compose stop postgres redis meilisearch)
  fi
}

cmd_status() {
  echo "Services:"
  status_proc "backend"    "${BACKEND_PID}"
  status_proc "celery"     "${CELERY_PID}"
  status_proc "frontend"   "${FRONTEND_PID}"
  status_proc "log_viewer" "${LOG_VIEWER_PID}"
  status_proc "ngrok"      "${NGROK_PID}"
  if is_running "${NGROK_PID}"; then
    echo "    Inspector: http://localhost:4040"
    echo "    Log file:  ${NGROK_LOG}"
    echo "    Tunnels:"
    if ! print_tunnels; then
      echo "      (no tunnels reported; ngrok still starting?)"
    fi
    local url
    if url="$(curl -s --max-time 1 "${NGROK_API}" 2>/dev/null \
        | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for t in (d.get("tunnels") or []):
    if t.get("proto") == "https":
        print(t.get("public_url", ""))
        break
' 2>/dev/null)" && [ -n "${url}" ]; then
      echo "    Logs URL:  ${url}/dev-logs/"
    fi
  fi
  echo
  echo "Docker:"
  (cd "${REPO_ROOT}" && docker compose ps postgres redis meilisearch) || true
}

cmd_logs() {
  local target="${1:-}"
  case "${target}" in
    backend)    exec tail -f "${BACKEND_LOG}" ;;
    celery)     exec tail -f "${CELERY_LOG}" ;;
    frontend)   exec tail -f "${FRONTEND_LOG}" ;;
    ngrok)      exec tail -f "${NGROK_LOG}" ;;
    log_viewer) exec tail -f "${LOG_VIEWER_LOG}" ;;
    "")         exec tail -f "${BACKEND_LOG}" "${CELERY_LOG}" "${FRONTEND_LOG}" ;;
    *) echo "Unknown log: ${target} (backend|celery|frontend|ngrok|log_viewer)" >&2; exit 1 ;;
  esac
}

cmd_restart() {
  cmd_stop
  cmd_start
}

cmd_reset() {
  # Hard reset: stop everything, wipe docker volumes, pull fresh images,
  # recreate containers from scratch, re-apply migrations + reseed the DB,
  # then restart all app processes. Destroys all local DB / Redis /
  # Meilisearch state — interactive confirmation required unless --yes.
  local with_tunnel=0
  local assume_yes=0
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --tunnel) with_tunnel=1; shift ;;
      --yes|-y) assume_yes=1; shift ;;
      *) echo "Unknown reset arg: $1" >&2; exit 1 ;;
    esac
  done

  require_command docker
  require_command uv
  require_command npm

  if ! docker compose version >/dev/null 2>&1; then
    echo "docker compose not available" >&2
    exit 1
  fi

  if [ "${assume_yes}" -ne 1 ]; then
    cat <<EOF
About to HARD RESET local dev state. This will:
  - Stop ngrok, log viewer, frontend, celery, backend
  - 'docker compose down -v' (deletes postgres / redis / meilisearch volumes)
  - 'docker compose pull' to refresh images
  - Recreate containers from scratch
  - Apply alembic migrations and reseed the dev DB
  - Restart backend, celery, frontend, log viewer$([ "${with_tunnel}" -eq 1 ] && echo " (and ngrok)")

ALL local data in those services will be lost.
EOF
    read -r -p "Type 'reset' to confirm: " confirm
    if [ "${confirm}" != "reset" ]; then
      echo "Aborted."
      exit 1
    fi
  fi

  # Guard against pointing this at a non-local DB/Redis URL.
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

  echo "Stopping app processes..."
  cmd_stop

  echo "Tearing down docker stack (volumes included)..."
  (cd "${REPO_ROOT}" && docker compose down -v --remove-orphans)

  # Belt-and-braces: nuke any stragglers that survived compose down (e.g. left
  # behind by an aborted previous run with a stale project name).
  for container_name in khanabazaar-postgres khanabazaar-redis khanabazaar-meilisearch; do
    if docker container inspect "${container_name}" >/dev/null 2>&1; then
      docker rm -f "${container_name}" >/dev/null
    fi
  done

  echo "Pulling fresh images..."
  (cd "${REPO_ROOT}" && docker compose pull postgres redis meilisearch)

  echo "Recreating containers..."
  (cd "${REPO_ROOT}" && docker compose up -d --force-recreate postgres redis meilisearch)

  # Three-stage postgres readiness. pg_isready only checks the listener is up.
  # Unix-socket psql becomes ready before the TCP listener stabilizes on a
  # freshly-initialized volume — postmaster briefly restarts while initdb
  # finishes. The migration step runs asyncpg over TCP from the host, so
  # gate on a real TCP query (`psql -h 127.0.0.1`) to match that path.
  for attempt in $(seq 1 60); do
    if (cd "${REPO_ROOT}" && docker compose exec -T postgres pg_isready -U postgres -d khanabazaar >/dev/null 2>&1); then
      break
    fi
    [ "${attempt}" -eq 60 ] && { echo "Postgres did not become ready (pg_isready)" >&2; exit 1; }
    sleep 1
  done

  for attempt in $(seq 1 60); do
    if (cd "${REPO_ROOT}" && PGPASSWORD=password docker compose exec -T postgres psql -h 127.0.0.1 -U postgres -d khanabazaar -tAc 'SELECT 1' >/dev/null 2>&1); then
      break
    fi
    [ "${attempt}" -eq 60 ] && { echo "Postgres did not accept TCP queries" >&2; exit 1; }
    sleep 1
  done

  for attempt in $(seq 1 60); do
    if curl -fsS --max-time 1 http://localhost:7700/health >/dev/null 2>&1; then
      break
    fi
    [ "${attempt}" -eq 60 ] && { echo "Meilisearch did not become ready" >&2; exit 1; }
    sleep 1
  done

  echo "Applying migrations and reseeding..."
  (
    cd "${BACKEND_APP_DIR}"
    uv run alembic upgrade head
    uv run python scripts/seed_database.py
    uv run python scripts/seed_database.py --verify-only
  )

  echo "Restarting app processes..."
  if [ "${with_tunnel}" -eq 1 ]; then
    cmd_start --tunnel
  else
    cmd_start
  fi

  echo
  echo "Hard reset complete."
}

usage() {
  cat <<EOF
Usage: $0 <command>

Commands:
  start              Start Postgres+Redis+Meilisearch (docker), backend, celery, frontend
  start --tunnel     Same as start, plus ngrok tunnels for :3000 + log viewer
  stop               Stop ngrok, log viewer, backend, celery, frontend (leaves docker running)
  stop --all         Also stop docker postgres+redis+meilisearch
  restart            Stop then start app processes
  reset              HARD RESET: stop everything, wipe docker volumes, pull
                     fresh images, recreate containers, re-apply migrations,
                     reseed DB, then restart all app processes.
                     Flags: --tunnel (also start ngrok), --yes / -y (skip prompt)
  status             Show pids + docker status (incl. ngrok URL when running)
  logs [name]        Tail logs (name: backend|celery|frontend|ngrok|log_viewer; default: all app logs)
  tunnel             Start ngrok tunnels (frontend + log viewer)
  tunnel-url         Print the current ngrok public URL (exits 1 if no tunnel)
EOF
}

case "${1:-}" in
  start)      shift; cmd_start "$@" ;;
  stop)       shift; cmd_stop "$@" ;;
  restart)    cmd_restart ;;
  reset)      shift; cmd_reset "$@" ;;
  status)     cmd_status ;;
  logs)       shift; cmd_logs "$@" ;;
  tunnel)     cmd_tunnel ;;
  tunnel-url) cmd_tunnel_url ;;
  ""|-h|--help) usage ;;
  *) usage; exit 1 ;;
esac
