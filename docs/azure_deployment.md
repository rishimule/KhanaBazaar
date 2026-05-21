<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Azure Deployment Guide

Production deployment plan for Khana Bazaar on Microsoft Azure. The stack favours managed PaaS over IaaS — no VMs, no Kubernetes, no kubelet babysitting. Everything provisions through Bicep + GitHub Actions.

> **Status:** target architecture for the move into production. Azure resources are not provisioned yet, and most of the deploy plumbing is **not yet committed**:
>
> - `infra/main.bicep`, `infra/main.parameters.json`, and `azure.yaml` — **not committed**.
> - `infra/modules/meilisearch.bicep` — **committed**.
> - All other Bicep modules listed in §6 — **not committed**.
> - `backend/app/Dockerfile`, `backend/app/Dockerfile.worker`, `frontend/Dockerfile` — **not committed**.
> - `.github/workflows/deploy.yml` — **not committed**. Only `.github/workflows/lint.yml` (Ruff + advisory Mypy on push/PR to `main`) currently exists.
>
> Treat the rest of this document as the implementation spec; tracked under Phase 5 in `TODO.md`.

---

## 1. Service Map

| Khana Bazaar component         | Azure service                                              | Tier (starting)              |
|--------------------------------|------------------------------------------------------------|------------------------------|
| FastAPI backend (`khanabazaar-api`)   | Azure Container Apps                               | Consumption (0.5 vCPU / 1 GiB) |
| Celery worker (`khanabazaar-worker`) | Azure Container Apps (internal, no ingress)        | Consumption                  |
| Celery beat scheduler (`khanabazaar-beat`) | Azure Container Apps (internal, single replica)  | Consumption                  |
| Next.js frontend (`khanabazaar-web`)  | Azure Container Apps (with public ingress)         | Consumption                  |
| PostgreSQL 15                  | Azure Database for PostgreSQL — Flexible Server           | Burstable `B1ms`             |
| Redis 7                        | Azure Cache for Redis                                      | Basic `C0` (250 MB)          |
| Meilisearch v1.11              | Azure Container App + Azure Files (internal-only ingress)  | Consumption (1 vCPU / 2 GiB) |
| Container images               | Azure Container Registry                                   | Basic                        |
| Secrets (JWT, OTP pepper, Resend, DB) | Azure Key Vault                                     | Standard                     |
| Logs / metrics / traces        | Azure Monitor + Application Insights + Log Analytics       | Pay-as-you-go                |
| CDN, WAF, custom domain, TLS   | Azure Front Door (Premium — required for managed WAF rules + Private Link to Container Apps) | Premium                     |
| DNS                            | Azure DNS                                                  | Standard                     |
| Identity for CI/CD             | Microsoft Entra ID — Workload Identity Federation          | Free                         |

All services live in **Central India** (`centralindia`) for proximity to users. Failover region: **South India** (`southindia`) — used only for Postgres geo-backups and a paused Front Door origin.

---

## 2. Topology

```
                              ┌──────────────────────────┐
                              │   Azure Front Door       │  TLS, WAF, CDN
                              │   (custom domain)        │
                              └────────┬─────────────────┘
                                       │
            ┌──────────────────────────┴─────────────────────────────┐
            ▼                                                          ▼
 ┌──────────────────────────┐                            ┌──────────────────────────┐
 │  Container App: web      │                            │  Container App: api      │
 │  Next.js (Node 20)       │  ── Bearer JWT, REST ────▶ │  FastAPI (Python 3.12)   │
 │  Public ingress          │                            │  Public ingress          │
 └──────────────────────────┘                            └────────┬─────────────────┘
                                                                  │
                                                  Private VNet integration
                                                                  │
                                  ┌───────────────────────────────┼───────────────────────────────┐
                                  ▼                               ▼                               ▼
                       ┌────────────────────┐         ┌──────────────────────┐        ┌──────────────────────┐
                       │ Postgres Flexible  │         │ Azure Cache for Redis│        │ Container App: worker│
                       │ private endpoint   │         │ private endpoint     │        │ Celery, no ingress   │
                       └────────────────────┘         └──────────┬───────────┘        └──────────┬───────────┘
                                                                 ▲                               │
                                                                 └───────────────────────────────┘
                                                                       broker (private)
```

- All five Container Apps live in the same **Container Apps Environment**, deployed into a **dedicated VNet**. Use a **workload-profile environment** (with all apps placed on the default Consumption profile). Legacy Consumption-only envs do support custom VNets, but they cannot receive Front Door Private Link traffic and cannot route through a NAT Gateway or UDR — both required here. The env should be created with `vnetConfiguration.internal: true` for the strictest ingress lockdown (otherwise app-level `external: false` is your only guarantee).
- The VNet has at minimum two subnets: an **infrastructure subnet delegated to `Microsoft.App/environments`** (Container Apps env attaches here, no other resources) and a **separate non-delegated subnet** that holds the Postgres + Redis + ACR + Key Vault **private endpoints**. Both subnets sit in the same VNet so DNS resolution flows.
- Private DNS zones — `privatelink.postgres.database.azure.com`, `privatelink.redis.cache.windows.net`, `privatelink.azurecr.io`, `privatelink.vaultcore.azure.net` — are **VNet-linked** to the Container Apps VNet so the apps resolve PE hostnames to private IPs.
- Front Door is the only public ingress. On Premium tier, Front Door → Container Apps **Private Link** keeps the api/web apps `external: false`. On Standard tier, both apps remain external and rely on app-layer `X-Azure-FDID` header validation (see §7.9).

---

## 3. Prerequisites

- Azure subscription with `Owner` (or `Contributor` + `User Access Administrator`) at the subscription scope.
- Azure CLI ≥ 2.60 and `azd` (Azure Developer CLI) ≥ 1.10.
- Bicep CLI ≥ 0.27 (bundled with `az`).
- GitHub repo with Actions enabled, admin permission to add OIDC federated credentials.
- Domain registered (`khanabazaar.in` or similar). DNS will move to Azure DNS.
- Resend account: API key + verified sender domain (production email).

---

## 4. Resource Layout

One subscription, two resource groups:

| Resource group        | Contents                                                                 |
|-----------------------|--------------------------------------------------------------------------|
| `kb-prod-rg`          | Container Apps Env, Container Apps, Postgres, Redis, ACR, Key Vault, Log Analytics, App Insights |
| `kb-network-rg`       | VNet, subnets, private DNS zones, Front Door, Azure DNS zone             |

Naming convention: `kb-<env>-<service>-<region-short>`. Examples: `kb-prod-api-cin`, `kb-prod-pg-cin`, `kb-prod-kv-cin`. Stick to it — half the Bicep is parameterised on it.

---

## 5. First-Time Provisioning

The infra lives in `infra/` (Bicep + `azd` config). Run from repo root:

```bash
az login
azd auth login
azd env new prod                      # creates .azure/prod/
azd env set AZURE_LOCATION centralindia
azd env set AZURE_SUBSCRIPTION_ID <sub-id>
azd up                                # provisions infra + builds + deploys
```

`azd up` does, in order:

1. Resolves Bicep, runs `az deployment sub create` against the subscription (`azd provision`).
2. Builds Docker images for `api`, `worker`, `beat`, `web` and pushes them to `kbprodacrcin.azurecr.io`.
3. Creates revisions on each Container App pointing at the new image tags (`azd deploy`).

> **Migration sequencing is not built into `azd up`.** `azd` has no native pre-deploy hook for running a Container Apps Job. Two ways to interlock migrations:
> - **Preferred — GitHub Actions** (§8): `provision` → `acr build` → `containerapp job update + start` → poll for `Succeeded` → `containerapp update` to flip revisions.
> - **Local — `azd hooks`** in `azure.yaml`:
>   ```yaml
>   hooks:
>     predeploy:
>       posix:
>         shell: sh
>         run: |
>           az containerapp job update --name kb-prod-migrate-cin -g kb-prod-rg \
>             --image kbprodacrcin.azurecr.io/khanabazaar-api:${AZURE_IMAGE_TAG}
>           az containerapp job start  --name kb-prod-migrate-cin -g kb-prod-rg
>           ./scripts/wait-job.sh kb-prod-migrate-cin kb-prod-rg
>   ```
>   Without one of these, an `azd up` will flip API revisions **before** the new migration has run.

First run takes 12–18 minutes. Postgres provisioning is the long pole (~6 min).

After it returns, `azd env get-values` shows the public Front Door URL plus per-app FQDNs.

---

## 6. Bicep Module Layout

```
infra/
  main.bicep                # subscription-scoped entrypoint                 [TBD]
  main.parameters.json      # per-env params (read by azd)                   [TBD]
  modules/
    network.bicep           # VNet, subnets, private DNS zones               [TBD]
    container-env.bicep     # Container Apps Environment + Log Analytics    [TBD]
    acr.bicep                                                                [TBD]
    keyvault.bicep                                                           [TBD]
    postgres.bicep          # Flexible Server + private endpoint             [TBD]
    redis.bicep             # Cache + private endpoint                       [TBD]
    appinsights.bicep                                                        [TBD]
    container-app-api.bicep                                                  [TBD]
    container-app-worker.bicep   # runs `celery worker` (KEDA-scaled)       [TBD]
    container-app-beat.bicep     # runs `celery beat` (pinned to 1 replica) [TBD]
    container-app-web.bicep                                                  [TBD]
    container-app-meili.bicep    # wrapper around meilisearch.bicep         [TBD]
    meilisearch.bicep            # Meilisearch + Azure Files share          [committed]
    migration-job.bicep     # Container Apps Job for `alembic upgrade head`  [TBD]
    frontdoor.bicep                                                          [TBD]
azure.yaml                  # azd service map (api, worker, web, meili)      [TBD]
```

Today only `infra/modules/meilisearch.bicep` exists; `infra/README.md` shows how it will plug into the future `main.bicep`. The rest of the modules below are the target shape, not what is on disk.

`azure.yaml` (top-level, **not yet committed**) tells `azd` which service maps to which Container App:

```yaml
name: khanabazaar
services:
  api:
    project: backend/app
    language: python
    host: containerapp
    docker:
      path: Dockerfile
      context: .
  worker:
    project: backend/app
    language: python
    host: containerapp
    docker:
      path: Dockerfile.worker
      context: .
  beat:
    # Reuses the worker image; beat-specific entrypoint comes from Bicep
    # `template.containers[].command` (`celery -A app.core.celery_app beat ...`).
    project: backend/app
    language: python
    host: containerapp
    docker:
      path: Dockerfile.worker
      context: .
  web:
    project: frontend
    language: ts
    host: containerapp
    docker:
      path: Dockerfile
      context: .
```

None of the three referenced Dockerfiles exist yet (`Dockerfile`, `Dockerfile.worker`, `frontend/Dockerfile`). The `beat` service shares the worker image — the only difference is the Celery command, supplied in `container-app-beat.bicep`. Add the Dockerfiles under Phase 5 before the first `azd up`.

**Build-context note.** `azd` resolves `docker.context` **relative to `project`**, not the repo root. With `project: backend/app` + `context: .`, the build context is `backend/app/` — fine for backend (`pyproject.toml`, `src/`, `migrations/` all live there). With `project: frontend` + `context: .`, the context is `frontend/` which already contains `messages/`, `src/i18n/`, `next.config.ts` — confirm `frontend/.dockerignore` does **not** exclude `messages/` or `src/i18n/`. If a Dockerfile ever needs repo-root files (e.g. shared `LICENSE`), set `context: ../..` and adjust `path:` accordingly.

---

## 7. Service-by-Service Configuration

### 7.1 `kb-prod-api-cin` (FastAPI)

- **Image**: `kbprodacrcin.azurecr.io/khanabazaar-api:<git-sha>`
- **Ingress**: external, target port `8000`, transport `auto` (HTTP/2 capable). Restricted to Front Door via `X-Azure-FDID` header rule.
- **Scale**: min 1, max 5. Rule: `http-scaling` at 80 concurrent requests per replica.
- **Probes**: liveness + readiness on `GET /health` (200 expected).
- **Identity**: system-assigned managed identity. Granted `Key Vault Secrets User` on `kb-prod-kv-cin`.

Env vars (referenced via Key Vault where secret):

| Key                    | Value / Source                                                  |
|------------------------|-----------------------------------------------------------------|
| `PYTHON_VERSION`       | `3.12` (image base)                                             |
| `PROJECT_NAME`         | `Khana Bazaar API`                                              |
| `ENVIRONMENT`          | `production`                                                    |
| `DATABASE_URL`         | Key Vault secret `database-url` (`postgresql+asyncpg://…`)      |
| `REDIS_URL`            | Key Vault secret `redis-url`                                    |
| `JWT_SECRET`           | Key Vault secret `jwt-secret` (auto-generated on first deploy)  |
| `JWT_EXPIRES_HOURS`    | `24`                                                            |
| `OTP_PEPPER`           | Key Vault secret `otp-pepper`                                   |
| `OTP_TTL_SECONDS`      | `600`                                                           |
| `OTP_MAX_ATTEMPTS`     | `5`                                                             |
| `OTP_RESEND_COOLDOWN`  | `60`                                                            |
| `OTP_MAX_PER_HOUR`     | `5`                                                             |
| `EMAIL_PROVIDER`       | `resend`                                                        |
| `RESEND_API_KEY`       | Key Vault secret `resend-api-key`                               |
| `RESEND_FROM_EMAIL`    | Key Vault secret `resend-from-email`                            |
| `SUPPORT_EMAIL`        | Plain env var (not Key Vault). e.g. `support@khanabazaar.in` — destination inbox for `/customers/me/support` messages. Default in `config.py` is `support@khanabazaar.example`; override per environment. |
| `SMS_PROVIDER`         | `twilio`                                                        |
| `TWILIO_ACCOUNT_SID`   | Key Vault secret `twilio-account-sid`                           |
| `TWILIO_AUTH_TOKEN`    | Key Vault secret `twilio-auth-token`                            |
| `TWILIO_FROM_NUMBER`   | Key Vault secret `twilio-from-number` (E.164, e.g. `+15005550006`) |
| `FRONTEND_ORIGIN`      | `https://www.khanabazaar.in,https://khanabazaar.in` — comma-separated; `core/config.py` exposes `Settings.cors_origins` which `app/__init__.py` feeds straight into `CORSMiddleware`. |
| `GOOGLE_MAPS_SERVER_API_KEY` | Key Vault secret `google-maps-server-api-key` (IP-restricted in GCP console to the Container App's outbound NAT) |
| `GOOGLE_MAPS_BROWSER_API_KEY` | Key Vault secret `google-maps-browser-api-key` (referrer-restricted; passed to the web container at build time as `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY`) |
| `GEO_RATE_LIMIT_PER_MIN` | `30` (default; bump per region if needed) |
| `GEO_AUTOCOMPLETE_CACHE_TTL_SECONDS` | `60` |
| `GEO_REVERSE_CACHE_TTL_SECONDS` | `86400` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | from `kb-prod-appi-cin`                              |

### 7.2 `kb-prod-worker-cin` (Celery worker) + `kb-prod-beat-cin` (Celery beat)

Beat must be split into a **separate Container App** from the worker. Container Apps applies a single scale rule per app and scales **all containers** in the app in lockstep — a multi-container app would run beat on every replica and double-fire scheduled tasks. Two distinct apps, one image, two entrypoints:

**`kb-prod-worker-cin` (worker)**
- **Image**: `kbprodacrcin.azurecr.io/khanabazaar-worker:<git-sha>` (same Python codebase, worker entrypoint).
- **Entrypoint**: `uv run celery -A app.core.celery_app worker --concurrency 2 --loglevel=info`.
- **Ingress**: disabled.
- **Scale**: min 1, max 3. KEDA `redis-lists` scaler. **Container Apps wraps KEDA**, so the `auth` shape is the Container Apps `secretRef` + `triggerParameter` form, not the vanilla KEDA `TriggerAuthentication`/`secretTargetRef` shape. Bicep:
  ```bicep
  // Container App secrets[] block (declared once per app):
  secrets: [
    { name: 'redis-password', keyVaultUrl: '${kv.properties.vaultUri}secrets/redis-password', identity: 'system' }
  ]
  // Scale rule:
  scale: {
    minReplicas: 1
    maxReplicas: 3
    rules: [{
      name: 'celery-queue-depth'
      custom: {
        type: 'redis-lists'
        metadata: {
          // `address` is "host:port"; alternatively use `host` + `port` keys.
          address: 'kb-prod-redis-cin.redis.cache.windows.net:6380'
          listName: 'celery'
          listLength: '10'        // scale up when > 10 queued
          enableTLS: 'true'
          databaseIndex: '0'      // KEDA renders all metadata as strings
        }
        auth: [
          { secretRef: 'redis-password', triggerParameter: 'password' }
        ]
      }
    }]
  }
  ```
  All metadata values are strings (KEDA convention). `redis-password` must be declared in the Container App's `secrets[]` array first — KEDA cannot reach Key Vault directly.
- **Identity**: system-assigned, same Key Vault grants as the API.

**`kb-prod-beat-cin` (beat scheduler)**
- **Image**: same `khanabazaar-worker:<git-sha>` image, beat entrypoint.
- **Entrypoint**: `uv run celery -A app.core.celery_app beat --loglevel=info --schedule /tmp/celerybeat-schedule`.
- **Ingress**: disabled.
- **Scale**: `minReplicas: 1`, `maxReplicas: 1` (no scaler — beat must never run concurrently).
- **Beat schedule** (in `core/celery_app.py`): `search.reconcile_index` hourly per kind (product, store) + daily deep pass, `search.verify_drift` nightly 04:30 UTC (legacy safety net), `search.rebuild_search_terms` nightly 03:15 UTC, `search.prune_query_log` daily 04:00 UTC.

Env vars (both apps, identical to API where overlapping): `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `OTP_PEPPER`, `SUPPORT_EMAIL`, `EMAIL_PROVIDER`, `RESEND_*`, `MEILI_URL`, `MEILI_MASTER_KEY`, `SEARCH_*`. Neither needs OTP rate-limit nor SMS settings (SMS dispatch is inline in the API container, not Celery).

### 7.3 `kb-prod-web-cin` (Next.js)

- **Image**: `kbprodacrcin.azurecr.io/khanabazaar-web:<git-sha>` — Next.js 16 build. `next.config.ts` does **not** yet enable `output: "standalone"`; add it before building the Docker image so the runtime stage can copy `.next/standalone` + `.next/static` instead of the full `node_modules` tree.
- **next-intl**: the frontend wraps `next.config.ts` with `createNextIntlPlugin("./src/i18n/request.ts")` and ships locale bundles from `frontend/messages/{en,hi,mr,gu,pa}.json`. The `messages/` directory must be present in the build context — confirm `.dockerignore` does not exclude it.
- **Ingress**: external, target port `3000`, locked to Front Door.
- **Scale**: min 1, max 4. HTTP scaling at 100 concurrent requests per replica.

Env vars:

| Key                  | Value                                                               |
|----------------------|---------------------------------------------------------------------|
| `NODE_VERSION`       | `20` (image base)                                                   |
| `NEXT_PUBLIC_API_URL`| `https://api.khanabazaar.in` (inlined at **build** time)            |
| `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY` | Key Vault `google-maps-browser-api-key` injected at build time (referrer-restricted) |

`NEXT_PUBLIC_*` is baked into the bundle by `next build`, so the build pipeline must be re-run for any URL change. The Bicep + GitHub Actions flow rebuilds the image automatically when this var changes in `azd env`.

### 7.4 Postgres Flexible Server (`kb-prod-pg-cin`)

- Version 15, **Burstable B1ms** (1 vCPU, 2 GiB), 32 GiB storage with auto-grow on.
- **Public access disabled** — only reachable via the VNet private endpoint.
- High availability: **off** at B1ms (not supported). Geo-redundant backups enabled.
- Backups: 7-day retention, geo-redundant. Point-in-time restore supported.
- `azure.extensions = uuid-ossp,pg_trgm,postgis,postgis_topology` in server parameters (lowercase enum values; PostGIS is required for the address `geo` GENERATED column + `ST_DWithin` distance queries; the local image is `postgis/postgis:15-3.4` for parity).
- Connection string handed to apps as `database-url` Key Vault secret in the form `postgresql+asyncpg://kbadmin:<pwd>@kb-prod-pg-cin.postgres.database.azure.com:5432/khanabazaar?sslmode=require` (libpq-style; asyncpg accepts it, `ssl=require` is JDBC-only).
- **Admin password lifecycle**: Bicep's `newGuid()` is non-deterministic — a second `azd up` will mint a new password and silently rotate it. The naive fix (`existing` lookup on the Key Vault secret) has a chicken-and-egg problem on the **first** deploy because `existing` fails when the secret doesn't yet exist. Two clean options:
  - **Two-phase deploy**: a thin `kv-secret-init.bicep` module creates the placeholder secret on first deploy (idempotent via stable `module` name + cached outputs); subsequent deploys read it via `kv.getSecret('pg-admin-password')`.
  - **Entra-only auth** (preferred long-term): provision the Postgres server with Microsoft Entra authentication enabled, grant the Container Apps' user-assigned managed identity the `Microsoft Entra Admin` role on the server, and drop the SQL password entirely. asyncpg can fetch an Entra access token via `azure-identity` and pass it as the password. Removes the entire rotation surface.

### 7.5 Azure Cache for Redis (`kb-prod-redis-cin`)

- Tier **Basic C0** (250 MB, no SLA, no HA — fine for OTP cache + Celery broker at our size).
- TLS-only on port `6380`.
- Public network access **disabled**; private endpoint into the VNet.
- `maxmemory-policy = noeviction` (Celery requires it; eviction silently drops queued tasks).

Connection string: `rediss://:<key>@kb-prod-redis-cin.redis.cache.windows.net:6380/0`.

### 7.5b Meilisearch (`kb-prod-meili-cin`)

- Azure Container App running `getmeili/meilisearch:v1.11`.
- **Internal-only ingress** on target port `7700` — never exposed to the public Front Door. Reached by `kb-prod-api-cin`, `kb-prod-worker-cin`, and `kb-prod-beat-cin` over the environment's private network. The committed Bicep uses `transport: 'tcp'` for simplicity (Meilisearch's HTTP is passed through transparently), but `transport: 'http'` is the more idiomatic choice for an HTTP-speaking service and unlocks Container Apps HTTP-aware observability (request metrics, latency histograms). Either works; the consumers reach it as `http://kb-prod-meili-cin:7700` regardless.
- 1 vCPU / 2 GiB starting; vertical scale if ~100k+ docs.
- **Persistent storage**: Azure Files share `meili-data` mounted at `/meili_data` (Meilisearch's LMDB store needs durable disk; Container App ephemeral storage would lose data on restart). The storage account key is embedded inline in the env's `storages[]` definition via `listKeys()` — rotating the key requires a Bicep redeploy. The `allowInsecure: true` ingress flag in the Bicep is **only valid because ingress is internal-only**; if it ever gets flipped to `external: true`, drop `allowInsecure` and require HTTPS.
- Master key in Key Vault (`meili-master-key`), referenced by the API + worker apps as the `MEILI_MASTER_KEY` env var. The same key is supplied to the Meilisearch container via `secretRef`.
- Replicas pinned to `1` — Meilisearch is single-writer, single-reader.
- Health probe: `GET /health` returns `{"status":"available"}`.
- Bicep: `infra/modules/meilisearch.bicep` is committed. Wire-up snippet for `main.bicep` lives in `infra/README.md`.

**Backend env vars wired in `kb-prod-api-cin`, `kb-prod-worker-cin`, and `kb-prod-beat-cin`:**

```
MEILI_URL=http://kb-prod-meili-cin:7700
MEILI_MASTER_KEY=<secretref:meili-master-key>     # see §7.7 — two-step KV reference
SEARCH_RATE_LIMIT_SUGGEST_PER_MIN=60
SEARCH_RATE_LIMIT_PRODUCTS_PER_MIN=30
SEARCH_SUGGEST_CACHE_TTL_SECONDS=60
SEARCH_SERVICEABLE_GRID_TTL_SECONDS=60
```

`@Microsoft.KeyVault(...)` is an **App Service / Functions** syntax — Container Apps does **not** accept it. Use the two-step pattern (Container App `secrets[]` block referencing Key Vault via `keyVaultUrl` + managed `identity`, then env var with `secretRef`). See §7.7 for details. The committed `infra/modules/meilisearch.bicep` already uses the correct `@secure()` parameter pattern; `main.bicep` is expected to inject the Key Vault value into the module's `meiliMasterKey` parameter.

**Startup behavior:** the API container's FastAPI `startup` handler calls `app.search.bootstrap.ensure_indexes(...)`, which **creates the three indexes (`products`, `stores`, `search_terms`) and pushes settings** if `SETTINGS_VERSION` differs from the marker. It does **not** populate documents — that's the reindex step. A failure here is logged and swallowed so the API still boots when Meilisearch is unavailable.

**First-deploy runbook:**

1. Apply Bicep: `azd up` (provisions the Meilisearch Container App + Azure Files share).
2. Trigger initial population from a one-shot Container Apps Job (or `az containerapp exec` into the API container):
   ```bash
   uv run python -m app.search.reindex --all                  # everything, in-place
   # or, zero-downtime live re-push of a single index:
   uv run python -m app.search.reindex --products --swap-on-finish
   # or, catch-up window:
   uv run python -m app.search.reindex --products --since 24h
   ```
   Flags: `--products`, `--stores`, `--search-terms`, `--all`, `--swap-on-finish`, `--since <duration>`.
3. Smoke: `curl -s 'http://kb-prod-meili-cin:7700/health'` returns `available`; `curl -s 'https://kb-prod-api-cin/api/v1/search/suggest?q=milk'` returns hits.
4. Route public traffic. Until reindex finishes, `/api/v1/search/*` returns empty arrays.

**Recovery from disk loss:** re-run step 2. The DB is the source of truth.

**Sync drift mitigation:** the Celery beat schedule (`core/celery_app.py`) runs `search.reconcile_index` for `product` and `store` kinds **hourly** plus a deep daily pass, alongside the legacy `search.verify_drift` task nightly at 04:30 UTC, plus `search.rebuild_search_terms` (03:15 UTC nightly) and `search.prune_query_log` (04:00 UTC daily). The reconciler walks the DB → Meilisearch and persists a summary at Redis key `search:reconcile:last:{kind}` for ops tooling to read. Verify the beat scheduler is actually running in the `kb-prod-beat-cin` app; without it, drift recovers only on a full reindex.

**Dead-letter queue:** failed Meilisearch sync attempts land in Redis sets `search:dlq:product` and `search:dlq:store` (see `app/search/dlq.py`). The reconciler drains them on every pass. Alert when set cardinality stays > N for M minutes — that's the early signal of a sustained Meilisearch outage.

### 7.6 Azure Container Registry (`kbprodacrcin`)

- Basic SKU.
- Admin user **disabled**. Pull access granted to each Container App's managed identity via `AcrPull` role.

### 7.7 Azure Key Vault (`kb-prod-kv-cin`)

Secrets:

| Name                | Origin                                              |
|---------------------|-----------------------------------------------------|
| `database-url`      | Built from Postgres FQDN + admin password (Bicep generates pwd via `newGuid()`). |
| `redis-url`         | Built from Redis primary key.                       |
| `jwt-secret`        | Generate manually before first deploy: `openssl rand -hex 32 \| az keyvault secret set --vault-name kb-prod-kv-cin --name jwt-secret --value @-`. Do **not** generate inside Bicep via `uniqueString()` — it is deterministic across redeploys (looks like rotation, isn't). Rotate by re-running the command. |
| `otp-pepper`        | Same pattern with `openssl rand -hex 16`. Rotating invalidates in-flight OTPs (acceptable; 10-min TTL). |
| `resend-api-key`    | Pulled from GitHub Actions secret `RESEND_API_KEY` and uploaded by `azd up`. |
| `google-maps-server-api-key` | Pulled from GitHub Actions secret `GOOGLE_MAPS_SERVER_API_KEY`. IP-restrict to the Container App's outbound IPs in GCP console. |
| `google-maps-browser-api-key` | Pulled from GitHub Actions secret `GOOGLE_MAPS_BROWSER_API_KEY`. HTTP-referrer-restrict to `https://*.khanabazaar.in/*` in GCP console. |
| `resend-from-email` | Same.                                               |
| `twilio-account-sid` | Pulled from GitHub Actions secret `TWILIO_ACCOUNT_SID`. |
| `twilio-auth-token`  | Pulled from GitHub Actions secret `TWILIO_AUTH_TOKEN`. |
| `twilio-from-number` | Pulled from GitHub Actions secret `TWILIO_FROM_NUMBER` (E.164). |

Container Apps Key Vault references are a **two-step** pattern (the App Service `@Microsoft.KeyVault(...)` syntax is **not supported**):

1. Define a Container App secret that references Key Vault:
   ```bicep
   secrets: [
     {
       name: 'database-url'
       keyVaultUrl: '${kv.properties.vaultUri}secrets/database-url'
       identity: 'system'   // or a user-assigned MI resource id
     }
   ]
   ```
2. Reference the secret by name from an env var:
   ```bicep
   env: [
     { name: 'DATABASE_URL', secretRef: 'database-url' }
   ]
   ```

CLI equivalent: `az containerapp create ... --secrets "database-url=keyvaultref:<KV-URI>,identityref:<MI-id>"`. The system-assigned MI must have the `Key Vault Secrets User` role on the vault before the secret is referenced — otherwise the app will fail to start with a synthetic secret-resolution error. See [Container Apps manage-secrets](https://learn.microsoft.com/azure/container-apps/manage-secrets).

### 7.8 Application Insights + Log Analytics

- Workspace `kb-prod-law-cin`, retention 30 days.
- App Insights `kb-prod-appi-cin` connected to the workspace.
- Connection string injected into both API and worker via env var. Python OpenCensus / OpenTelemetry SDK is wired in `app/main.py` only when `APPLICATIONINSIGHTS_CONNECTION_STRING` is set.

### 7.9 Azure Front Door (`kb-prod-fd`)

- **Tier: Premium**, not Standard. The OWASP / Microsoft-managed DRS rule sets and Private-Link-to-origin are both **Premium-only** features ([WAF tuning](https://learn.microsoft.com/azure/web-application-firewall/afds/waf-front-door-tuning), [AFD + Container Apps](https://learn.microsoft.com/azure/container-apps/how-to-integrate-with-azure-front-door)). If launching on Standard for cost reasons, drop the managed rule set and rely on custom rules only.
- Two origin groups:
  - `web-origin` → `kb-prod-web-cin` Container App FQDN
  - `api-origin` → `kb-prod-api-cin` Container App FQDN
- Routes:
  - `/api/*` → `api-origin`
  - everything else → `web-origin`
- WAF policy in Prevention mode with the Microsoft-managed DRS rule set (Premium-only — see tier note above).
- Custom domain `khanabazaar.in` + `www.khanabazaar.in` with managed TLS certs.
- **Origin lock-down**: Container Apps has no native "Front Door only" header rule (App Service's `X-Azure-FDID` access restriction does not exist on Container Apps). Two options:
  - **Premium:** Front Door → Container Apps Private Link, set the Container App ingress to `external: false` so it is unreachable except through Front Door.
  - **Standard:** keep ingress external and enforce the `X-Azure-FDID` header check inside FastAPI as middleware (read the expected GUID from a Key Vault secret, reject mismatches with 403). This is an app-layer guard, not a platform guarantee.

---

## 8. CI/CD with GitHub Actions

> Today only `.github/workflows/lint.yml` exists — Ruff on push/PR to `main`, with Mypy run as advisory (`|| true`). Pytest is intentionally excluded from CI to keep PR feedback fast; run it locally before merging. The deploy workflow below is the **target** pipeline.

`.github/workflows/deploy.yml` (not yet committed) triggers on push to `main`. Pipeline:

1. **Lint + type-check + test** — `ruff`, `mypy`, `pytest` (backend); `npm run lint`, `next build` (frontend).
2. **Login to Azure** — OIDC via `azure/login@v2` using a Workload Identity federated credential (no client secret stored in GitHub).
3. **Build + push images** — `az acr build --registry kbprodacrcin --image khanabazaar-api:$GITHUB_SHA backend/app` (and similarly for worker / web). ACR Tasks does the build cloud-side; runner doesn't need Docker. (ACR Basic SKU does support Tasks / `az acr build`.)
4. **Run migrations** — point the migration Job at the new image, then start it:
   ```bash
   az containerapp job update --name kb-prod-migrate-cin -g kb-prod-rg \
     --image kbprodacrcin.azurecr.io/khanabazaar-api:$GITHUB_SHA
   az containerapp job start  --name kb-prod-migrate-cin -g kb-prod-rg
   ```
   `--image-name` does **not** exist on `az containerapp job start` (it belongs to `az acr build`). The execution name is returned by `start`; poll it with `az containerapp job execution show ... --query 'properties.status'` until `Succeeded`. Non-zero exit fails the workflow before any app revision flips.
5. **Update Container Apps** — `az containerapp update --name <app> -g kb-prod-rg --image kbprodacrcin.azurecr.io/<image>:$GITHUB_SHA --revision-suffix gh${GITHUB_RUN_NUMBER}-$(echo $GITHUB_SHA | cut -c1-7)`. Revision mode is `single`, so each update creates a new revision and shifts 100% traffic once health probes pass. The `--revision-suffix` gives revisions debuggable names instead of opaque hashes; without it, retried deploys with the same SHA collide on revision names. Old revisions are retained per `maxInactiveRevisions: 5` (under `properties.configuration`; platform-default is undocumented — empirically ~100, set explicitly to 5 so rollback targets stay predictable). `revisionRetention` is **not** a valid property.
6. **Smoke test** — `curl https://api.khanabazaar.in/health` must return `{"status":"ok"}`.

Federated credential setup (one-off):

```bash
az ad app create --display-name khanabazaar-gh-deploy
az ad sp create --id <app-id>
# Contributor on BOTH resource groups — kb-prod-rg holds the apps, kb-network-rg holds Front Door + private DNS zones.
az role assignment create --assignee <sp-id> --role Contributor --scope /subscriptions/<sub-id>/resourceGroups/kb-prod-rg
az role assignment create --assignee <sp-id> --role Contributor --scope /subscriptions/<sub-id>/resourceGroups/kb-network-rg
# Branch-scoped credential for push-to-main deploys.
az ad app federated-credential create --id <app-id> --parameters '{
  "name": "github-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:rishimule/KhanaBazaar:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}'
# Second credential for PR-trigger jobs (lint, plan-only). Required — branch-scoped subjects do NOT match `pull_request` events.
az ad app federated-credential create --id <app-id> --parameters '{
  "name": "github-pr",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:rishimule/KhanaBazaar:pull_request",
  "audiences": ["api://AzureADTokenExchange"]
}'
```

---

## 9. Database Migrations

Migrations run as a **Container Apps Job** (`kb-prod-migrate-cin`). Bicep shape (exact property names):

```bicep
resource migrate 'Microsoft.App/jobs@2024-03-01' = {
  name: 'kb-prod-migrate-cin'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    environmentId: env.id
    configuration: {
      triggerType: 'Manual'
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      replicaTimeout: 600          // sibling of manualTriggerConfig, not nested
      replicaRetryLimit: 0
      secrets: [
        {
          name: 'database-url'
          keyVaultUrl: '${kv.properties.vaultUri}secrets/database-url'
          identity: 'system'
        }
      ]
      registries: [
        { server: acr.properties.loginServer, identity: 'system' }
      ]
    }
    template: {
      containers: [
        {
          name: 'migrate'
          image: '<placeholder — overwritten by CI job update>'
          command: ['uv', 'run', 'alembic', 'upgrade', 'head']
          env: [
            { name: 'DATABASE_URL', secretRef: 'database-url' }
          ]
        }
      ]
    }
  }
}
```

Jobs have their own `secrets[]` block — they do **not** inherit secrets from sibling Container Apps. CI invocation:

```bash
az containerapp job update --name kb-prod-migrate-cin -g kb-prod-rg \
  --image kbprodacrcin.azurecr.io/khanabazaar-api:$GITHUB_SHA
az containerapp job start  --name kb-prod-migrate-cin -g kb-prod-rg
```

The CI workflow polls `az containerapp job execution show` until status is `Succeeded`. Failure aborts the deploy before traffic moves.

Pitfalls:

- **Long migrations**: Job replica timeout is 600 s; bump it before shipping a heavy backfill, or run the migration manually from a Cloud Shell.
- **Irreversible changes**: use expand/contract — migration that adds the new shape, deploy, backfill, later release drops the old shape. There is no automatic rollback for schema.
- **`ALTER TABLE` locks**: Postgres `ALTER TABLE` takes `ACCESS EXCLUSIVE`. Use `CREATE INDEX CONCURRENTLY` and explicit transactional batching for hot tables.

---

## 10. Rolling Out Updates

| Action                       | How                                                                                  |
|------------------------------|--------------------------------------------------------------------------------------|
| Deploy latest commit         | Push to `main` (GitHub Actions deploys all three apps + runs migrations).            |
| Deploy a different commit    | `azd deploy --service api --from-package <image-tag>` or rerun the workflow with a chosen ref. |
| Roll back (single-revision mode) | `az containerapp update --name kb-prod-api-cin -g kb-prod-rg --image kbprodacrcin.azurecr.io/khanabazaar-api:<previous-sha>` — re-deploys the previous image as a new revision; stays in single-revision mode. `az containerapp revision activate` is **not valid** in single mode (returns `RevisionOperationNotAllowed`). |
| Roll back with traffic split | Set `--revision-mode Multiple` first, then `az containerapp ingress traffic set ... --revision-weight <previous>=100 <current>=0`. |
| Pause auto-deploy            | Disable the GitHub Actions workflow (Settings → Actions → Disable workflow).         |
| Hotfix without CI            | `azd deploy --service api` from a developer machine after `azd auth login`.          |

Container Apps keeps the last 5 inactive revisions warm (`maxInactiveRevisions: 5`). Revision metadata + image tags are immutable, so a previous image tag is always reachable in ACR.

---

## 11. Custom Domain & TLS

1. Delegate `khanabazaar.in` to Azure DNS (NS records at registrar).
2. Front Door → **Domains → Add custom domain** → validate via Azure-managed TXT record. Front Door issues and renews the TLS cert automatically.
3. Update CNAME / ALIAS at apex (`khanabazaar.in`) to the Front Door endpoint.
4. After cert is live, re-deploy the `web` Container App with the production `NEXT_PUBLIC_API_URL=https://api.khanabazaar.in` so the bundle inlines the right URL.
5. Update `FRONTEND_ORIGIN` on the API to the production frontend URL list.

---

## 12. CORS

CORS is config-driven. `backend/app/src/app/core/config.py` defines:

```python
FRONTEND_ORIGIN: str = "http://localhost:3000,http://127.0.0.1:3000"

@property
def cors_origins(self) -> list[str]:
    return [o.strip() for o in self.FRONTEND_ORIGIN.split(",") if o.strip()]
```

and `backend/app/src/app/__init__.py` passes `settings.cors_origins` straight into `CORSMiddleware`. To allow production traffic, just set `FRONTEND_ORIGIN` on `kb-prod-api-cin`:

```
FRONTEND_ORIGIN=https://www.khanabazaar.in,https://khanabazaar.in
```

Set the same value via `azd env set FRONTEND_ORIGIN '…'` so Bicep can wire it into the Container App env block. No code change needed at launch.

---

## 13. Observability

- **Logs**: Container Apps stream `stdout` + `stderr` to Log Analytics. Query in the Azure Portal → Log Analytics → `ContainerAppConsoleLogs_CL`.
- **App Insights wiring is not yet implemented in the codebase.** `app/main.py` is 8 lines and only runs `uvicorn.run(...)`; no OpenTelemetry / OpenCensus SDK is imported anywhere in `backend/app/src/`. Before launch, add `azure-monitor-opentelemetry` to `pyproject.toml` and call `configure_azure_monitor()` inside `app/__init__.py` guarded on `settings.APPLICATIONINSIGHTS_CONNECTION_STRING`. Once wired, the Live Metrics blade is the closest equivalent to `tail -f`.
- **CLI tail**: `az containerapp logs show --name kb-prod-api-cin --resource-group kb-prod-rg --follow --tail 200`.
- **Exec into a replica**: `az containerapp exec --name kb-prod-api-cin --resource-group kb-prod-rg --command sh`. For multi-container apps (today only meili is single-container, but planned), add `--container <name>` — required when an app holds more than one container.

Common issues:

| Symptom                                          | Likely cause / fix                                                              |
|--------------------------------------------------|---------------------------------------------------------------------------------|
| API 500 on every request                         | `DATABASE_URL` driver mismatch — `core/config.py` rewrites `postgres://` to `postgresql+asyncpg://`; confirm the validator runs and Key Vault secret has the right scheme. |
| Migration job exits with `alembic.util.CommandError: Multiple head revisions` | Branch divergence — rebase migration history, generate a merge revision, redeploy. |
| Worker logs `kombu.exceptions.OperationalError` on boot | Redis cold connection retries; usually resolves in <30 s. If persistent, confirm `REDIS_URL` resolves to the private endpoint, not the public FQDN. |
| Frontend hits `localhost:8000` in production     | `NEXT_PUBLIC_API_URL` set after build — re-run the GitHub Actions deploy so `next build` re-inlines the URL. |
| Browser console: CORS error                      | `FRONTEND_ORIGIN` env var missing on `kb-prod-api-cin`, or value does not match the request `Origin` header (scheme + host + port) — see §12. |
| API boot crash: `ValidationError JWT_SECRET field required` | Key Vault reference broken (managed identity missing `Secrets User` role, or secret rotated/disabled). Check Key Vault access policies. |
| Container App stuck in `Activating` revision     | Image pull failure — confirm ACR `AcrPull` role assignment on the app's managed identity. |

---

## 14. Scaling

| Component         | Vertical                                                          | Horizontal                                                       |
|-------------------|-------------------------------------------------------------------|------------------------------------------------------------------|
| API Container App | Bump CPU/memory in revision template (e.g. 1.0 vCPU / 2 GiB).     | `scale.maxReplicas` up to 30 on Consumption.                     |
| Worker            | Same.                                                             | KEDA `redis` scaler tied to queue length — auto-scales on lag.   |
| Postgres          | Burstable → General Purpose D2ds → D4ds and up.                   | Read replicas on GP tier and above.                              |
| Redis             | Basic C0 → Standard C1 (HA) → Premium (clustering, persistence).  | Premium-tier clustering only.                                    |
| Front Door        | N/A — globally distributed.                                       | N/A.                                                             |

Worker concurrency lives in the Bicep template (Celery `--concurrency 2`); change it there so it's version-controlled, then redeploy. Beat must always run as a **separate Container App** (`kb-prod-beat-cin`, `minReplicas=maxReplicas=1`) — running beat inside the worker app (as a sidecar container or `--beat` flag) is unsafe because Container Apps scales **all containers in an app together**, which would double-fire every scheduled task on every worker replica. See §7.2.

---

## 15. Cost Expectations

Azure pricing changes; treat the starting tiers as a floor. Approximate monthly cost in `centralindia` at the configured tiers (USD, list price):

- Container Apps (4 apps — api, worker, beat, meili — Consumption, light load): ~$20–40
- Web Container App: ~$5–10
- Postgres Burstable B1ms: ~$15
- Azure Cache for Redis Basic C0: ~$16
- Azure Files (Meilisearch LMDB, 50 GiB LRS Standard): ~$3
- ACR Basic + Tasks build minutes: ~$5
- Private endpoints (Postgres + Redis + ACR + Key Vault ≈ 4 × $0.01/hr): ~$29, plus ~$0.01/GB inbound + outbound data processing (negligible at low traffic)
- Key Vault, Log Analytics, App Insights: ~$5–10 with low log volume
- Azure Front Door Premium: **~$330/mo baseline** (10 endpoints + 5 custom domains + managed WAF included), + ~$0.22/GB egress (first 10 TB) + ~$1/million requests. Standard is ~$35/mo baseline but lacks the managed WAF rule set + Private Link to Container Apps (see §7.9). The Front Door price model was reworked in 2024–2025 — verify against the [pricing calculator](https://azure.microsoft.com/pricing/calculator/) before budgeting.
- Azure DNS: ~$1

Total at idle: **~$430–470/month on Premium Front Door**, or **~$135–160/month if launching on Standard Front Door without managed WAF**. Use the pricing calculator for accurate estimates and watch the cost analysis blade weekly. Private endpoints are a meaningful but secondary line item; the single biggest cost driver is the Front Door tier — consider whether the managed WAF rule set is worth the 10× tier premium vs. enforcing equivalents in app middleware.

---

## 16. Disaster Recovery

- **Postgres backups**: 7-day retention, geo-redundant. Restore via Portal → Postgres server → **Restore**, choose point-in-time (UTC). Restore creates a new server; repoint Key Vault `database-url` and redeploy.
- **Manual backup**: Postgres is private-endpoint-only, so `pg_dump` cannot run from a random laptop or stock GitHub runner. Use a one-shot Container Apps Job inside the env:
  ```bicep
  // infra/modules/pg-backup-job.bicep
  resource pgBackup 'Microsoft.App/jobs@2024-03-01' = {
    name: 'kb-prod-pg-backup-cin'
    properties: {
      environmentId: env.id
      configuration: {
        triggerType: 'Manual'
        manualTriggerConfig: { parallelism: 1, replicaCompletionCount: 1 }
        replicaTimeout: 3600
        secrets: [
          { name: 'database-url', keyVaultUrl: '...', identity: 'system' }
        ]
      }
      template: {
        containers: [{
          name: 'pg-dump'
          image: 'postgres:15-alpine'
          command: ['sh', '-c', 'pg_dump "$DATABASE_URL" | gzip > /backup/pg-$(date +%F).sql.gz']
          env: [{ name: 'DATABASE_URL', secretRef: 'database-url' }]
          volumeMounts: [{ volumeName: 'backup-share', mountPath: '/backup' }]
        }]
        volumes: [{ name: 'backup-share', storageType: 'AzureFile', storageName: 'pgBackupStorage' }]
      }
    }
  }
  ```
  Trigger nightly via `az containerapp job start`, or wire it into a cron-style schedule (`triggerType: 'Schedule'`, `scheduleTriggerConfig.cronExpression: '0 3 * * *'`).
- **Redis**: ephemeral. Celery queues survive restarts because `noeviction` is set, but Redis is cache-only — no app state should require Redis durability. Premium tier offers persistence if that ever changes.
- **Container images**: ACR retains all pushed tags. `git-sha` tags are immutable and reproducible.
- **Source**: GitHub is the source of truth. Bicep + `azd up` rebuilds the entire stack from any commit.

Recommended cadence: nightly `pg_dump` to a separate storage account on top of Azure's geo-redundant backups.

---

## 17. Local Production-Mode Smoke Test

Before pushing to `main`, exercise the production codepath locally to catch build-time issues (TS errors, missing env vars inlined into the bundle, Alembic drift).

### Backend

```bash
cd backend/app
ENVIRONMENT=production \
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/khanabazaar \
REDIS_URL=redis://localhost:6379/0 \
JWT_SECRET=$(openssl rand -hex 32) \
OTP_PEPPER=$(openssl rand -hex 16) \
EMAIL_PROVIDER=console \
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run build
NEXT_PUBLIC_API_URL=http://localhost:8000 npm start
```

Unlike `npm run dev`, this build inlines `NEXT_PUBLIC_API_URL` into the bundle so the browser hits `localhost:8000` **directly**, bypassing the `next.config.ts` `/api/v1/*` rewrite — exactly what happens in prod (where the inlined value is `https://api.khanabazaar.in`). Two implications:
- CORS is exercised. Set `FRONTEND_ORIGIN=http://localhost:3000` on the backend or expect rejections.
- The dev-only `/dev-logs` proxy rewrite is also gone — log-viewer routes will 404, which is fine for a prod-mode smoke test.

### Container build dry run

```bash
az acr build --registry kbprodacrcin --image khanabazaar-api:dryrun backend/app
```

Catches Dockerfile + dependency resolution issues without touching production revisions.

---

## 18. References

- [Azure Container Apps overview](https://learn.microsoft.com/azure/container-apps/overview)
- [Container Apps secrets + Key Vault references](https://learn.microsoft.com/azure/container-apps/manage-secrets)
- [Azure Database for PostgreSQL — Flexible Server](https://learn.microsoft.com/azure/postgresql/flexible-server/overview)
- [Azure Cache for Redis](https://learn.microsoft.com/azure/azure-cache-for-redis/cache-overview)
- [Azure Front Door Standard/Premium](https://learn.microsoft.com/azure/frontdoor/front-door-overview)
- [Bicep language docs](https://learn.microsoft.com/azure/azure-resource-manager/bicep/)
- [Azure Developer CLI (`azd`)](https://learn.microsoft.com/azure/developer/azure-developer-cli/overview)
- [GitHub Actions OIDC with Azure](https://learn.microsoft.com/azure/developer/github/connect-from-azure)
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/)
