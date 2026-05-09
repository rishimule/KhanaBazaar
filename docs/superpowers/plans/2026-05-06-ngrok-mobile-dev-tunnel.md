<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Ngrok Mobile Dev Tunnel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single-command ngrok tunnel to the dev workflow so the in-progress webapp is reachable on a phone for real-device testing during development, without exposing the FastAPI backend publicly.

**Architecture:** ngrok agent forwards `:3000` only. The Next.js dev server proxies `/api/v1/*` server-side to the loopback FastAPI on `:8000` via `next.config.ts` `rewrites()`. Frontend uses relative API paths in the browser, so the rotating ngrok URL needs no env wiring. `scripts/dev.sh` gains a `--tunnel` flag, two new subcommands (`tunnel`, `tunnel-url`), and folds ngrok into `start`/`stop`/`status` lifecycles.

**Tech Stack:** Next.js 16.1 App Router (`rewrites()`), bash, ngrok 3.x agent, ngrok local API (`http://localhost:4040/api/tunnels`), python3 (for JSON parse — already a project dep via `uv`).

**Spec:** See `docs/superpowers/specs/2026-05-06-ngrok-mobile-dev-design.md`.

**Pre-conditions (verified during brainstorming):**
- ngrok binary installed at `/usr/local/bin/ngrok`, version 3.39.1.
- ngrok auth token configured in `~/.config/ngrok/ngrok.yml`.
- python3 3.12 in PATH.
- `src/middleware.ts` matcher already excludes `api`, so next-intl will NOT intercept the rewrite.
- Zero RSC callers of `frontend/src/lib/api.ts` (every caller has `"use client"`).

---

## File Structure

| File | Responsibility | New / Modified |
|------|----------------|----------------|
| `frontend/next.config.ts` | Define the `/api/v1/*` rewrite to localhost:8000 | Modified |
| `frontend/.env.local` | Set `NEXT_PUBLIC_API_URL=""` so browser fetches go to current origin | Modified |
| `frontend/.env.example` | Mirror `.env.local` defaults for new clones | Modified |
| `scripts/dev.sh` | Add ngrok process management, flags, subcommands; reorder stop; expand status output | Modified |
| `docs/local_setup.md` | New "Mobile testing via ngrok" section + troubleshooting note | Modified |

No new files. No backend changes. No `package.json` / `pyproject.toml` changes.

---

## Task 1: Add Next.js rewrite + flip frontend env

**Goal:** Browser at any origin (localhost:3000 or ngrok host) can hit `/api/v1/*` and have Next.js dev server proxy server-side to FastAPI on `:8000`.

**Files:**
- Modify: `frontend/next.config.ts`
- Modify: `frontend/.env.local`
- Modify: `frontend/.env.example`

- [ ] **Step 1: Edit `frontend/next.config.ts`**

Replace the entire contents with:

```ts
import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: "http://localhost:8000/api/v1/:path*",
      },
    ];
  },
};

export default withNextIntl(nextConfig);
```

Note: the rewrite destination is the loopback backend. It is reached only by the Next dev server process, never by the phone or any external client.

- [ ] **Step 2: Edit `frontend/.env.local`**

Replace the line `NEXT_PUBLIC_API_URL="http://localhost:8000"` with:

```
# Empty = relative URLs. Browser sends /api/v1/* to current origin
# (localhost:3000 or the ngrok host) and Next.js rewrites() proxies
# server-side to http://localhost:8000.
#
# CRITICAL: Must be an explicit empty string. If this line is removed,
# the code fallback "http://localhost:8000" kicks in and breaks mobile
# (phone cannot reach the dev box's localhost). In production, override
# with the absolute backend URL.
NEXT_PUBLIC_API_URL=""
```

Leave the unrelated `NEXT_PUBLIC_FIREBASE_*` lines untouched.

- [ ] **Step 3: Edit `frontend/.env.example`**

Replace the existing `NEXT_PUBLIC_API_URL` block with the same comment + value as Step 2:

```
# Empty = relative URLs. Browser sends /api/v1/* to current origin
# (localhost:3000 or the ngrok host) and Next.js rewrites() proxies
# server-side to http://localhost:8000.
#
# CRITICAL: Must be an explicit empty string. If this line is removed,
# the code fallback "http://localhost:8000" kicks in and breaks mobile
# (phone cannot reach the dev box's localhost). In production, override
# with the absolute backend URL.
NEXT_PUBLIC_API_URL=""
```

- [ ] **Step 4: Verify rewrite works locally (no ngrok yet)**

Restart the frontend so it picks up the new config + env:

```bash
./scripts/dev.sh restart
```

Wait ~10 s for Next to recompile. Then in a desktop browser, hit:

```
http://localhost:3000/api/v1/meta/health
```

Expected: JSON response from the backend like `{"status":"ok",...}` (proves the rewrite proxies to `:8000`). If you get a Next 404 page, the rewrite didn't load — re-check `next.config.ts`.

- [ ] **Step 5: Verify the SPA still works locally**

Open `http://localhost:3000/` in a desktop browser. Confirm the home page renders, the navbar is interactive, and you can navigate to a stores page. Open DevTools → Network and confirm a request to `/api/v1/...` (relative URL, current origin) returns 200.

- [ ] **Step 6: Commit**

```bash
git add frontend/next.config.ts frontend/.env.local frontend/.env.example
git commit -m "feat(dev): proxy /api/v1 via Next.js rewrites for same-origin fetches"
```

---

## Task 2: Extend `scripts/dev.sh` with ngrok lifecycle

**Goal:** `./scripts/dev.sh start --tunnel` brings up the stack plus a public ngrok URL forwarding to `:3000`. New subcommands `tunnel` and `tunnel-url`. `stop` and `status` cover ngrok. `start` without `--tunnel` is unchanged.

**Files:**
- Modify: `scripts/dev.sh`

- [ ] **Step 1: Add ngrok PID/log path constants**

After the existing `FRONTEND_LOG="${LOG_DIR}/frontend.log"` line (around `scripts/dev.sh:18`), add:

```bash
NGROK_PID="${RUN_DIR}/ngrok.pid"
NGROK_LOG="${LOG_DIR}/ngrok.log"
NGROK_API="http://localhost:4040/api/tunnels"
```

- [ ] **Step 2: Add a tunnel-URL fetcher helper**

After the `status_proc()` function definition (currently ends near line 89), add:

```bash
fetch_tunnel_url() {
  # Polls ngrok's local agent API for up to ~10s and prints the first
  # public URL on stdout. Returns 0 if a URL is found, 1 otherwise.
  local attempt url
  for attempt in $(seq 1 20); do
    url="$(curl -s --max-time 1 "${NGROK_API}" 2>/dev/null \
      | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
tunnels = data.get("tunnels") or []
if tunnels:
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
```

- [ ] **Step 3: Add a `cmd_tunnel` function**

Add directly above `cmd_stop()` (currently at line 129):

```bash
cmd_tunnel() {
  require_command ngrok
  require_command curl
  require_command python3

  start_proc "ngrok"   "${NGROK_PID}"   "${NGROK_LOG}"   "${REPO_ROOT}" \
    ngrok http 3000 --log=stdout --log-format=logfmt

  echo -n "Resolving tunnel URL"
  local url
  if url="$(fetch_tunnel_url)"; then
    echo
    echo "Tunnel ready: ${url}  ->  :3000"
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
```

- [ ] **Step 4: Modify `cmd_start` to accept `--tunnel`**

Replace the entire `cmd_start()` function (currently lines 91–127) with:

```bash
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

  if [ "${with_tunnel}" -eq 1 ]; then
    cmd_tunnel
  fi

  echo
  echo "All services up."
  echo "  Backend:  http://localhost:8000  (docs: /docs)"
  echo "  Frontend: http://localhost:3000"
  if [ "${with_tunnel}" -eq 1 ] && is_running "${NGROK_PID}"; then
    local url
    if url="$(fetch_tunnel_url)"; then
      echo "  Tunnel:   ${url}  ->  :3000"
    fi
  fi
  echo "  Logs:     ${LOG_DIR}"
  echo "Run '${0} logs [backend|celery|frontend|ngrok]' to tail logs."
}
```

- [ ] **Step 5: Modify `cmd_stop` to kill ngrok first**

Replace the existing `cmd_stop()` function with:

```bash
cmd_stop() {
  stop_proc "ngrok"    "${NGROK_PID}"
  stop_proc "frontend" "${FRONTEND_PID}"
  stop_proc "celery"   "${CELERY_PID}"
  stop_proc "backend"  "${BACKEND_PID}"

  if [ "${1:-}" = "--all" ]; then
    echo "Stopping Docker services..."
    (cd "${REPO_ROOT}" && docker compose stop postgres redis)
  fi
}
```

- [ ] **Step 6: Modify `cmd_status` to surface ngrok**

Replace the existing `cmd_status()` function with:

```bash
cmd_status() {
  echo "Services:"
  status_proc "backend"  "${BACKEND_PID}"
  status_proc "celery"   "${CELERY_PID}"
  status_proc "frontend" "${FRONTEND_PID}"
  status_proc "ngrok"    "${NGROK_PID}"
  if is_running "${NGROK_PID}"; then
    local url
    if url="$(fetch_tunnel_url)"; then
      echo "    URL: ${url}"
    fi
  fi
  echo
  echo "Docker:"
  (cd "${REPO_ROOT}" && docker compose ps postgres redis) || true
}
```

- [ ] **Step 7: Modify `cmd_logs` to allow `ngrok`**

Replace the `cmd_logs()` function with:

```bash
cmd_logs() {
  local target="${1:-}"
  case "${target}" in
    backend)  exec tail -f "${BACKEND_LOG}" ;;
    celery)   exec tail -f "${CELERY_LOG}" ;;
    frontend) exec tail -f "${FRONTEND_LOG}" ;;
    ngrok)    exec tail -f "${NGROK_LOG}" ;;
    "")       exec tail -f "${BACKEND_LOG}" "${CELERY_LOG}" "${FRONTEND_LOG}" ;;
    *) echo "Unknown log: ${target} (backend|celery|frontend|ngrok)" >&2; exit 1 ;;
  esac
}
```

- [ ] **Step 8: Update `usage()` and the dispatch `case`**

Replace the `usage()` function and the trailing `case` block at the bottom of the file with:

```bash
usage() {
  cat <<EOF
Usage: $0 <command>

Commands:
  start              Start Postgres+Redis (docker), backend, celery, frontend
  start --tunnel     Same as start, plus an ngrok tunnel forwarding :3000
  stop               Stop ngrok, backend, celery, frontend (leaves docker running)
  stop --all         Also stop docker postgres+redis
  restart            Stop then start app processes
  status             Show pids + docker status (incl. ngrok URL when running)
  logs [name]        Tail logs (name: backend|celery|frontend|ngrok; default: all app logs)
  tunnel             Start an ngrok tunnel against an already-running frontend
  tunnel-url         Print the current ngrok public URL (exits 1 if no tunnel)
EOF
}

case "${1:-}" in
  start)      shift; cmd_start "$@" ;;
  stop)       shift; cmd_stop "$@" ;;
  restart)    cmd_restart ;;
  status)     cmd_status ;;
  logs)       shift; cmd_logs "$@" ;;
  tunnel)     cmd_tunnel ;;
  tunnel-url) cmd_tunnel_url ;;
  ""|-h|--help) usage ;;
  *) usage; exit 1 ;;
esac
```

- [ ] **Step 9: Smoke test the script syntax**

```bash
bash -n scripts/dev.sh
```

Expected: no output, exit 0. Any output indicates a syntax error to fix.

- [ ] **Step 10: Smoke test `start --tunnel`**

```bash
./scripts/dev.sh stop || true
./scripts/dev.sh start --tunnel
```

Expected output ends with a `Tunnel: https://...ngrok-free.app -> :3000` line. If the URL is missing but the line says "Tunnel started but URL unresolved", read `.dev/logs/ngrok.log` — usually an auth or network issue.

Also verify:

```bash
./scripts/dev.sh tunnel-url
```

Prints the same URL.

```bash
./scripts/dev.sh status
```

Lists ngrok as running with the URL underneath.

- [ ] **Step 11: Smoke test `stop`**

```bash
./scripts/dev.sh stop
pgrep -f "ngrok http 3000" && echo "STILL RUNNING — bug" || echo "ngrok exited cleanly"
```

Expected: "ngrok exited cleanly".

- [ ] **Step 12: Smoke test plain `start` (regression)**

```bash
./scripts/dev.sh start
./scripts/dev.sh status
```

Expected: backend/celery/frontend running, ngrok stopped (no tunnel started). Confirms `start` without `--tunnel` is unchanged.

- [ ] **Step 13: Commit**

```bash
git add scripts/dev.sh
git commit -m "feat(dev): add ngrok tunnel lifecycle to dev.sh"
```

---

## Task 3: Document mobile testing in `docs/local_setup.md`

**Goal:** New developer reading `local_setup.md` knows the one-liner and the gotchas.

**Files:**
- Modify: `docs/local_setup.md`

- [ ] **Step 1: Add a new section between "6. Verify the stack" and "7. Test database"**

Insert directly before the line `## 7. Test database` (currently line 141):

```markdown
## 6a. Mobile testing via ngrok (optional)

Open the in-progress webapp on a phone for real-device testing. ngrok must be installed and authenticated (`ngrok config add-authtoken <token>`) once.

```bash
./scripts/dev.sh start --tunnel
```

The script prints a public URL like `https://abc-123.ngrok-free.app`. Open it on the phone. ngrok serves a one-time interstitial warning page on first visit per device — click "Visit Site" — then the SPA loads.

How it works: ngrok forwards only port 3000 (the Next.js dev server). All `/api/v1/*` requests go same-origin to that URL and are proxied server-side by Next.js to the loopback FastAPI on :8000. The backend is never publicly reachable.

Useful while running:

```bash
./scripts/dev.sh tunnel-url     # print current public URL
./scripts/dev.sh status         # show services + tunnel URL
./scripts/dev.sh logs ngrok     # tail ngrok agent log
./scripts/dev.sh stop           # also kills the tunnel
```

Notes:

- The ngrok URL rotates on each restart on the free plan. The frontend uses relative API paths, so this is harmless to the app — only the URL you type into the phone changes.
- First request through the tunnel may briefly 502 while Next.js compiles the entry route. Reload after a few seconds.
- `NEXT_PUBLIC_API_URL` in `frontend/.env.local` must remain an empty string. If it is set to an absolute URL like `http://localhost:8000`, the phone tries to reach the dev box's localhost and fails. The default in `.env.example` is already correct.

```

- [ ] **Step 2: Update the troubleshooting tail**

Replace the final paragraph of the file (the existing **Frontend can't reach API** entry, currently the last line) with these two paragraphs:

```markdown
**Frontend can't reach API (localhost dev)** — confirm `NEXT_PUBLIC_API_URL` in `frontend/.env.local` is exactly `""` (empty string) and that the Next.js `rewrites()` block in `frontend/next.config.ts` proxies `/api/v1/:path*` to `http://localhost:8000/api/v1/:path*`. Restart `npm run dev` after editing either file.

**Phone can't reach API (ngrok tunnel)** — check `./scripts/dev.sh logs ngrok` for auth or quota errors. If the URL loads HTML but `/api/v1/*` returns 404, the Next.js `rewrites()` block is missing or malformed — see `next.config.ts`.
```

- [ ] **Step 3: Verify rendering**

```bash
grep -n "Mobile testing via ngrok" docs/local_setup.md
grep -n "Phone can't reach API" docs/local_setup.md
```

Both should return one line each.

- [ ] **Step 4: Commit**

```bash
git add docs/local_setup.md
git commit -m "docs(setup): document ngrok mobile testing flow"
```

---

## Task 4: End-to-end smoke test from a phone

**Goal:** Confirm the full feature works end-to-end on a real phone with mobile data (not on the same wifi).

**Files:** None modified. Manual test.

- [ ] **Step 1: Bring up the stack with the tunnel**

```bash
./scripts/dev.sh stop || true
./scripts/dev.sh start --tunnel
```

Note the printed `https://...ngrok-free.app` URL.

- [ ] **Step 2: Desktop browser sanity check**

Open the URL in desktop Chrome (not the same browser profile that has localhost cookies). Click through the ngrok interstitial. Verify the home page renders and the navbar is interactive.

- [ ] **Step 3: Phone (mobile data, NOT wifi) — home page**

Disable wifi on the phone, ensure mobile data is on. Open the ngrok URL in mobile Safari/Chrome. Click through the ngrok interstitial. Verify the home page renders, fonts load, navbar is interactive.

- [ ] **Step 4: Phone — OTP login**

Tap "Sign in" → enter any email → request OTP. The 6-digit code is in the backend stdout. Tail it from the dev box:

```bash
./scripts/dev.sh logs backend | grep "OTP"
```

Enter the code on the phone. Confirm the dashboard loads and `localStorage.kb_token` is set (DevTools remote inspect or a manual check).

- [ ] **Step 5: Phone — cart + checkout shell**

Browse to a stores page → pick a store → add a product to cart → open the cart → tap "Checkout". Confirm the address picker and payment method UI render. (No need to complete a real order — the MVP delivery flow stubs payment.)

- [ ] **Step 6: Desktop concurrent localhost still works**

In a desktop browser, open `http://localhost:3000/` in a fresh tab. Verify the home page still loads independently and a network call to `/api/v1/...` returns 200 in DevTools. This confirms there is no regression to the local-only workflow.

- [ ] **Step 7: Stop the stack**

```bash
./scripts/dev.sh stop
```

Reload the ngrok URL on the phone and confirm it returns "tunnel offline" (or browser connection error). The public surface is gone.

- [ ] **Step 8: No commit**

This task only verifies. If any step fails, fix the underlying file and commit the fix as `fix(dev): <what>`.

---

## Self-Review (run after writing this plan)

- **Spec coverage:** Components 5.1, 5.2, 5.3, doc update, security, and test plan all map to Tasks 1–4.
- **Placeholder scan:** No "TBD" / "TODO" / "implement later" entries. Every code block is concrete.
- **Type/name consistency:**
  - `NGROK_PID`, `NGROK_LOG`, `NGROK_API` defined in Step 1 of Task 2 and reused consistently.
  - `fetch_tunnel_url` defined once and reused.
  - `cmd_tunnel`, `cmd_tunnel_url` consistent across definition (Task 2 Step 3) and dispatch (Task 2 Step 8).
  - `--tunnel` flag handled identically in `cmd_start` (Task 2 Step 4) and surfaced in usage (Task 2 Step 8).
- **Idempotency / regression:** `start` without `--tunnel` (Task 2 Step 12) and Task 4 Step 6 both verify no regression to the existing flow.
- **Security:** Backend never exposed. `rewrites()` destination is loopback. Confirmed in spec section 6 and reflected in plan code.

---

## Rollback (if needed mid-implementation)

Each task is its own commit. To undo any task without affecting earlier ones, use `git revert <commit>`. Tasks are ordered so that reverting in reverse order leaves the working tree consistent at every point.
