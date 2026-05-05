#!/usr/bin/env bash
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

BACKEND_LOG="${LOG_DIR}/backend.log"
CELERY_LOG="${LOG_DIR}/celery.log"
FRONTEND_LOG="${LOG_DIR}/frontend.log"

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
  (
    cd "${workdir}"
    nohup "$@" >"${log_file}" 2>&1 &
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
  kill "${pid}" 2>/dev/null || true
  for _ in $(seq 1 20); do
    kill -0 "${pid}" 2>/dev/null || break
    sleep 0.25
  done
  if kill -0 "${pid}" 2>/dev/null; then
    echo "Force killing ${name}..."
    kill -9 "${pid}" 2>/dev/null || true
  fi
  pkill -P "${pid}" 2>/dev/null || true
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

cmd_start() {
  require_command docker
  require_command uv
  require_command npm

  if ! docker compose version >/dev/null 2>&1; then
    echo "docker compose not available" >&2
    exit 1
  fi

  echo "Bringing up Postgres + Redis..."
  (cd "${REPO_ROOT}" && docker compose up -d postgres redis)

  for attempt in $(seq 1 60); do
    if (cd "${REPO_ROOT}" && docker compose exec -T postgres pg_isready -U postgres -d khanabazaar >/dev/null 2>&1); then
      break
    fi
    [ "${attempt}" -eq 60 ] && { echo "Postgres did not become ready" >&2; exit 1; }
    sleep 1
  done

  start_proc "backend"  "${BACKEND_PID}"  "${BACKEND_LOG}"  "${BACKEND_APP_DIR}" \
    uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

  start_proc "celery"   "${CELERY_PID}"   "${CELERY_LOG}"   "${BACKEND_APP_DIR}" \
    uv run celery -A app.core.celery_app worker --loglevel=info

  start_proc "frontend" "${FRONTEND_PID}" "${FRONTEND_LOG}" "${FRONTEND_DIR}" \
    npm run dev

  echo
  echo "All services up."
  echo "  Backend:  http://localhost:8000  (docs: /docs)"
  echo "  Frontend: http://localhost:3000"
  echo "  Logs:     ${LOG_DIR}"
  echo "Run '${0} logs [backend|celery|frontend]' to tail logs."
}

cmd_stop() {
  stop_proc "frontend" "${FRONTEND_PID}"
  stop_proc "celery"   "${CELERY_PID}"
  stop_proc "backend"  "${BACKEND_PID}"

  if [ "${1:-}" = "--all" ]; then
    echo "Stopping Docker services..."
    (cd "${REPO_ROOT}" && docker compose stop postgres redis)
  fi
}

cmd_status() {
  echo "Services:"
  status_proc "backend"  "${BACKEND_PID}"
  status_proc "celery"   "${CELERY_PID}"
  status_proc "frontend" "${FRONTEND_PID}"
  echo
  echo "Docker:"
  (cd "${REPO_ROOT}" && docker compose ps postgres redis) || true
}

cmd_logs() {
  local target="${1:-}"
  case "${target}" in
    backend)  exec tail -f "${BACKEND_LOG}" ;;
    celery)   exec tail -f "${CELERY_LOG}" ;;
    frontend) exec tail -f "${FRONTEND_LOG}" ;;
    "")       exec tail -f "${BACKEND_LOG}" "${CELERY_LOG}" "${FRONTEND_LOG}" ;;
    *) echo "Unknown log: ${target} (backend|celery|frontend)" >&2; exit 1 ;;
  esac
}

cmd_restart() {
  cmd_stop
  cmd_start
}

usage() {
  cat <<EOF
Usage: $0 <command>

Commands:
  start            Start Postgres+Redis (docker), backend, celery, frontend
  stop             Stop backend, celery, frontend (leaves docker running)
  stop --all       Also stop docker postgres+redis
  restart          Stop then start app processes
  status           Show pids + docker status
  logs [name]      Tail logs (name: backend|celery|frontend; default: all)
EOF
}

case "${1:-}" in
  start)   cmd_start ;;
  stop)    shift; cmd_stop "$@" ;;
  restart) cmd_restart ;;
  status)  cmd_status ;;
  logs)    shift; cmd_logs "$@" ;;
  ""|-h|--help) usage ;;
  *) usage; exit 1 ;;
esac
