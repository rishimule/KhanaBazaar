<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Ngrok Mobile Dev Tunnel — Design Spec

**Date:** 2026-05-06
**Status:** Draft → ready for implementation plan
**Author:** Pair-design with Claude

## 1. Problem

Developer wants to open the in-progress webapp on a phone for real-device testing during local development. Phone is not necessarily on the same wifi network as the dev box. The current local stack binds backend to `:8000` and frontend to `:3000`, both reachable only on the developer host.

ngrok agent is already installed on the Linux dev box (v3.39.1) with auth token configured (`~/.config/ngrok/ngrok.yml`).

## 2. Goal

- One command (`./scripts/dev.sh start --tunnel`) brings up the full local stack and a public ngrok URL pointing at the frontend.
- Phone navigates to the URL, the webapp loads, OTP login works, cart works, end-to-end flows behave as on the desktop.
- Backend stays bound to loopback-only (no public surface).
- Local-only dev workflow (`./scripts/dev.sh start` without `--tunnel`) keeps working unchanged.
- No application code changes (only `next.config.ts`, env, and the dev script).

## 3. Non-goals

- Reserved/static ngrok domain. Free tier offers one — defer until URL rotation becomes friction.
- Exposing the FastAPI backend through a second tunnel. (See "Approach Considered: B" below for why.)
- Production tunnel automation, CI integration, or any sharing flow beyond developer-driven mobile testing.
- Auto-injecting the ngrok URL into backend `FRONTEND_ORIGIN` (CORS) — not required because all browser-visible API calls become same-origin via Next.js rewrites.

## 4. Approach

### Chosen: Single tunnel + Next.js `rewrites()` proxy (Option A)

ngrok exposes only the Next.js dev server on `:3000`. Next.js itself proxies `/api/v1/*` server-side to the local FastAPI on `:8000` via the `rewrites()` config option. Browser sees same-origin everywhere.

```
phone browser
   │ HTTPS
   ▼
https://<rotating>.ngrok-free.app   (ngrok agent → :3000)
   │
   ▼
Next.js dev server (:3000)
   ├── serves React/RSC + static
   └── rewrites: /api/v1/* → http://localhost:8000/api/v1/*  (loopback)
                                                      │
                                                      ▼
                                                FastAPI (:8000)
```

**Why this works:**
- Same-origin in the browser → no CORS, no preflight, no `FRONTEND_ORIGIN` env juggling.
- ngrok URL rotation is harmless because the frontend never templates the public URL into requests — paths stay relative.
- ngrok-free.app provides HTTPS, satisfying service worker / PWA requirements on the phone.
- Backend stays loopback-only from outside the box.

### Approach considered: Two tunnels for frontend + backend (Option B)

Run `ngrok start --all` against an `ngrok.yml` with two tunnel definitions, then have `dev.sh` poll `http://localhost:4040/api/tunnels` for both URLs and rewrite `NEXT_PUBLIC_API_URL` + `FRONTEND_ORIGIN` into env files before starting services.

**Rejected** because:
- Doubles moving parts (env mutation, restart ordering, two URL fetches with retry).
- Publicly exposes the backend's OTP request endpoint, DB writes, etc. — measurable attack surface increase for zero gain.
- The only thing it unlocks (hitting the API directly from the phone or external tools) has no current use case in this codebase. `/docs` works fine from the desktop.

### Approach considered: LAN-only (Option C)

Bind frontend to `0.0.0.0:3000`, phone on the same wifi hits `http://<dev-host-ip>:3000`. **Rejected** because the user explicitly asked for ngrok and wants tunnel-based access not constrained to a single wifi network.

## 5. Components

| File | Change | Reversible |
|------|--------|------------|
| `frontend/next.config.ts` | Add `async rewrites()` block proxying `/api/v1/:path*` to `http://localhost:8000/api/v1/:path*` | yes |
| `frontend/.env.local` | Set `NEXT_PUBLIC_API_URL=""` (empty string, with explanatory comment) | yes |
| `frontend/.env.example` | Same flip + comment so new clones are correct out of the box | yes |
| `scripts/dev.sh` | Add ngrok process management, `start --tunnel` flag, `tunnel` and `tunnel-url` subcommands; fold tunnel into `stop` and `status` | yes |
| `docs/local_setup.md` | Add "Mobile testing via ngrok" section | yes |

**Files NOT changed:**
- `frontend/src/lib/api.ts` and `frontend/src/lib/AuthContext.tsx` both read `process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"`. With the env explicitly set to `""`, the templated URL becomes `/api/v1/...` (relative). Both files are client-only (every caller has `"use client"`), so no SSR/RSC absolute-URL requirement applies.
- Backend (`backend/app/...`): zero change. Still binds `0.0.0.0:8000`.
- `frontend/src/middleware.ts`: matcher already excludes `api`, so next-intl will not intercept `/api/v1/*` and the rewrite fires cleanly.
- Production build: untouched. Production env supplies an absolute `NEXT_PUBLIC_API_URL`.

### 5.1 `frontend/next.config.ts`

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

`allowedDevOrigins` (Next 15.2+ console-warning silencer for cross-origin dev requests) is intentionally omitted. The app functions without it; only a noisy warning is suppressed by setting it. Add later if the warning becomes annoying.

### 5.2 `frontend/.env.local` and `.env.example`

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

### 5.3 `scripts/dev.sh`

New process tracked alongside backend/celery/frontend:
- PID file: `${RUN_DIR}/ngrok.pid`
- Log file: `${LOG_DIR}/ngrok.log`

Reuses existing `start_proc` / `stop_proc` / `status_proc` helpers. ngrok agent is a single foreground process; `kill PID` is sufficient.

**ngrok command:** `ngrok http 3000 --log=stdout --log-format=logfmt`

**URL discovery:** After spawning ngrok, poll `http://localhost:4040/api/tunnels` (ngrok's local agent API, default port) until `tunnels[0].public_url` is present. Timeout 10 s, interval 0.5 s. Parse via `python3 -c` (no `jq` dependency).

**New / changed commands:**

```
./scripts/dev.sh start              # local only (unchanged)
./scripts/dev.sh start --tunnel     # local + ngrok :3000 tunnel
./scripts/dev.sh tunnel             # start tunnel only (services running)
./scripts/dev.sh tunnel-url         # print current public URL or exit 1
./scripts/dev.sh stop               # stops backend, celery, frontend, AND tunnel
./scripts/dev.sh stop --all         # also stops docker postgres+redis (unchanged)
./scripts/dev.sh status             # also shows tunnel + URL when running
```

**Output on `start --tunnel` success:**

```
All services up.
  Backend:  http://localhost:8000  (docs: /docs)
  Frontend: http://localhost:3000
  Tunnel:   https://xxxx-xx-xx-xx-xx.ngrok-free.app  → :3000
  Logs:     .dev/logs
```

**Order in `start --tunnel`:** docker → backend → celery → frontend → ngrok. ngrok last because (a) frontend takes ~5–10 s to compile on first start; tunnel without it would 502 briefly anyway, and (b) keeping ngrok last makes it easy to kill cleanly first in `stop`.

**Stop order:** ngrok first (kills public surface immediately), then frontend → celery → backend.

**Failure modes handled:**
- `ngrok` binary missing: `require_command ngrok` is invoked **only** when `--tunnel` flag is passed (or when `tunnel` subcommand runs). Plain `start` does not require ngrok.
- ngrok auth missing or invalid: ngrok agent exits with error in log; `is_running` check fails after `sleep 0.3`; existing helper tails log to stderr. User sees the actual ngrok error.
- ngrok agent local API port 4040 in use: URL fetch loop times out → script prints "tunnel started but URL unresolved, see `.dev/logs/ngrok.log`" and exits 0 (does not fail the whole start).
- Frontend not yet listening when tunnel starts: ngrok is fine — it forwards once :3000 binds. First mobile request may receive 502 until Next finishes compiling. Documented in test plan.

## 6. Security

- **Backend never publicly reachable.** ngrok forwards only to `:3000`.
- **HTTPS by default** via `ngrok-free.app` certificate. JWT in `localStorage` not snoopable on transit.
- **No new public endpoints**, no CORS widening, no Host header trust assumptions changed.
- **ngrok free-tier interstitial:** ngrok injects a one-time browser warning page when first hitting an `*.ngrok-free.app` URL on a given device. ngrok serves it only for `text/html` navigation responses, not for `fetch`/XHR. So one click-through per device per ngrok URL is enough; subsequent SPA fetches and the service worker work without extra handling.
- **JWT storage:** unchanged (still `localStorage`, key `kb_token`). Same-origin via rewrites means no SameSite cookie surprises.

## 7. Testing

No automated frontend tests in repo. Manual test plan:

1. `./scripts/dev.sh start --tunnel` — verify URL printed.
2. **Desktop browser** opens ngrok URL → click ngrok interstitial → home page renders, navbar interactive.
3. **Phone on mobile data** (not wifi) opens URL → home page renders.
4. **Phone:** OTP login flow — request OTP, locate code in `console` provider log (`.dev/logs/backend.log`), submit, dashboard loads.
5. **Phone:** add product to cart, navigate to checkout, see address picker, payment method selector.
6. **Desktop concurrent:** `http://localhost:3000` continues to work unchanged in another tab/browser.
7. `./scripts/dev.sh stop` — `ngrok` process exits (verify via `pgrep ngrok`), public URL returns 404/connection refused.
8. `./scripts/dev.sh start` (no flag) — confirm tunnel does NOT start, no ngrok dependency invoked.
9. **First-request 502** — first phone request after `start --tunnel` may briefly 502 while Next.js compiles the entry route. Reload after ~5–10 s.

## 8. Rollback

Revert the five file edits (`next.config.ts`, `frontend/.env.local`, `frontend/.env.example`, `scripts/dev.sh`, `docs/local_setup.md`). No DB migrations. No backend changes. No PR-level coupling. Anyone on the team unaffected because rewrites and the empty env are backward-compatible with the old workflow (browser at `localhost:3000` still functions identically — paths get rewritten in the same way, just locally).

## 9. Future-proofing notes

- **Rewrites apply only to inbound HTTP into Next.js.** They do NOT intercept server-side `fetch()` calls from React Server Components or route handlers. Any future RSC that calls the backend directly must use an absolute URL (e.g., `http://localhost:8000` in dev, prod URL in prod). Recommend introducing a separate `BACKEND_INTERNAL_URL` env var when the first such caller appears, and branching in `api.ts` on `typeof window === "undefined"`.
- **Hardcoded `localhost:8000`** appears in both the rewrite destination and `dev.sh` uvicorn args. If the backend port ever becomes configurable, update both together (or read from a shared env var).
- **ngrok URL rotation** is acceptable today. If sharing the URL externally or pinning it for any reason, switch to the free reserved domain and document the override (e.g., `NGROK_DOMAIN=mydev.ngrok-free.app` env consumed by `dev.sh`).

## 10. Open questions

None. All ambiguities resolved during brainstorming pass.
