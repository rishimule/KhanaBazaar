<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Azure Deployment Guide

Production deployment plan for Khana Bazaar on Microsoft Azure. The stack favours managed PaaS over IaaS — no VMs, no Kubernetes, no kubelet babysitting. Everything provisions through Bicep + GitHub Actions.

> **Status:** target architecture for the move into production. Azure resources are not provisioned yet; this document is the blueprint we will execute.

---

## 1. Service Map

| Khana Bazaar component         | Azure service                                              | Tier (starting)              |
|--------------------------------|------------------------------------------------------------|------------------------------|
| FastAPI backend (`khanabazaar-api`)   | Azure Container Apps                               | Consumption (0.5 vCPU / 1 GiB) |
| Celery worker (`khanabazaar-worker`)  | Azure Container Apps (job-style, no ingress)       | Consumption                  |
| Next.js frontend (`khanabazaar-web`)  | Azure Container Apps (with public ingress)         | Consumption                  |
| PostgreSQL 15                  | Azure Database for PostgreSQL — Flexible Server           | Burstable `B1ms`             |
| Redis 7                        | Azure Cache for Redis                                      | Basic `C0` (250 MB)          |
| Container images               | Azure Container Registry                                   | Basic                        |
| Secrets (JWT, OTP pepper, Resend, DB) | Azure Key Vault                                     | Standard                     |
| Logs / metrics / traces        | Azure Monitor + Application Insights + Log Analytics       | Pay-as-you-go                |
| CDN, WAF, custom domain, TLS   | Azure Front Door (Standard)                                | Standard                     |
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

- All three Container Apps live in the same **Container Apps Environment** so they share a managed VNet.
- Postgres and Redis are reachable only via **private endpoints** inside that VNet. No public network exposure.
- Front Door is the only public ingress. Container App `web` and `api` accept traffic only from Front Door (validated via `X-Azure-FDID` header).

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

1. Resolves Bicep, runs `az deployment sub create` against the subscription.
2. Builds Docker images for `api`, `worker`, `web` and pushes them to `kbprodacrcin.azurecr.io`.
3. Creates revisions on each Container App pointing at the new image tags.
4. Runs the Alembic migration as a **Container Apps Job** (one-shot) before the API revision flips to `latestRevision`.

First run takes 12–18 minutes. Postgres provisioning is the long pole (~6 min).

After it returns, `azd env get-values` shows the public Front Door URL plus per-app FQDNs.

---

## 6. Bicep Module Layout

```
infra/
  main.bicep                # subscription-scoped entrypoint
  main.parameters.json      # per-env params (read by azd)
  modules/
    network.bicep           # VNet, subnets, private DNS zones
    container-env.bicep     # Container Apps Environment + Log Analytics
    acr.bicep
    keyvault.bicep
    postgres.bicep          # Flexible Server + private endpoint
    redis.bicep             # Cache + private endpoint
    appinsights.bicep
    container-app-api.bicep
    container-app-worker.bicep
    container-app-web.bicep
    migration-job.bicep     # Container Apps Job for `alembic upgrade head`
    frontdoor.bicep
azure.yaml                  # azd service map (api, worker, web)
```

`azure.yaml` (top-level) tells `azd` which service maps to which Container App:

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
  web:
    project: frontend
    language: ts
    host: containerapp
    docker:
      path: Dockerfile
      context: .
```

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
| `SMS_PROVIDER`         | `twilio`                                                        |
| `TWILIO_ACCOUNT_SID`   | Key Vault secret `twilio-account-sid`                           |
| `TWILIO_AUTH_TOKEN`    | Key Vault secret `twilio-auth-token`                            |
| `TWILIO_FROM_NUMBER`   | Key Vault secret `twilio-from-number` (E.164, e.g. `+15005550006`) |
| `FRONTEND_ORIGIN`      | `https://www.khanabazaar.in,https://khanabazaar.in`             |
| `GOOGLE_MAPS_SERVER_API_KEY` | Key Vault secret `google-maps-server-api-key` (IP-restricted in GCP console to the Container App's outbound NAT) |
| `GOOGLE_MAPS_BROWSER_API_KEY` | Key Vault secret `google-maps-browser-api-key` (referrer-restricted; passed to the web container at build time as `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY`) |
| `GEO_RATE_LIMIT_PER_MIN` | `30` (default; bump per region if needed) |
| `GEO_AUTOCOMPLETE_CACHE_TTL_SECONDS` | `60` |
| `GEO_REVERSE_CACHE_TTL_SECONDS` | `86400` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | from `kb-prod-appi-cin`                              |

### 7.2 `kb-prod-worker-cin` (Celery)

- **Image**: same registry, `khanabazaar-worker:<git-sha>` (same Python codebase, different entrypoint).
- **Ingress**: disabled (internal only — no traffic listening).
- **Scale**: min 1, max 3. Rule: `azure-servicebus`-style custom rule on Redis queue length via KEDA `redis` scaler (`listLength` on `celery` queue).
- **Identity**: system-assigned. Same Key Vault grants as the API.

Env vars: identical to API for `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `OTP_PEPPER`, `EMAIL_PROVIDER`, `RESEND_*`. Worker doesn't need OTP rate-limit settings or SMS settings (SMS is dispatched inline from the API container, not via Celery).

### 7.3 `kb-prod-web-cin` (Next.js)

- **Image**: `kbprodacrcin.azurecr.io/khanabazaar-web:<git-sha>` — Next.js standalone build (`output: "standalone"` in `next.config.ts`).
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
- `azure.extensions = uuid-ossp,pg_trgm,POSTGIS` in server parameters (PostGIS is required for the address `geo` GENERATED column + `ST_DWithin` distance queries; the local image is `postgis/postgis:15-3.4` for parity).
- Connection string handed to apps as `database-url` Key Vault secret in the form `postgresql+asyncpg://kbadmin:<pwd>@kb-prod-pg-cin.postgres.database.azure.com:5432/khanabazaar?ssl=require`.

### 7.5 Azure Cache for Redis (`kb-prod-redis-cin`)

- Tier **Basic C0** (250 MB, no SLA, no HA — fine for OTP cache + Celery broker at our size).
- TLS-only on port `6380`.
- Public network access **disabled**; private endpoint into the VNet.
- `maxmemory-policy = noeviction` (Celery requires it; eviction silently drops queued tasks).

Connection string: `rediss://:<key>@kb-prod-redis-cin.redis.cache.windows.net:6380/0`.

### 7.6 Azure Container Registry (`kbprodacrcin`)

- Basic SKU.
- Admin user **disabled**. Pull access granted to each Container App's managed identity via `AcrPull` role.

### 7.7 Azure Key Vault (`kb-prod-kv-cin`)

Secrets:

| Name                | Origin                                              |
|---------------------|-----------------------------------------------------|
| `database-url`      | Built from Postgres FQDN + admin password (Bicep generates pwd via `newGuid()`). |
| `redis-url`         | Built from Redis primary key.                       |
| `jwt-secret`        | Generated once in Bicep via `uniqueString(subscription().subscriptionId, deployment().name)` + `base64`; replace manually before launch with `openssl rand -hex 32`. |
| `otp-pepper`        | Same generation pattern. Rotate manually with `openssl rand -hex 16`. |
| `resend-api-key`    | Pulled from GitHub Actions secret `RESEND_API_KEY` and uploaded by `azd up`. |
| `google-maps-server-api-key` | Pulled from GitHub Actions secret `GOOGLE_MAPS_SERVER_API_KEY`. IP-restrict to the Container App's outbound IPs in GCP console. |
| `google-maps-browser-api-key` | Pulled from GitHub Actions secret `GOOGLE_MAPS_BROWSER_API_KEY`. HTTP-referrer-restrict to `https://*.khanabazaar.in/*` in GCP console. |
| `resend-from-email` | Same.                                               |
| `twilio-account-sid` | Pulled from GitHub Actions secret `TWILIO_ACCOUNT_SID`. |
| `twilio-auth-token`  | Pulled from GitHub Actions secret `TWILIO_AUTH_TOKEN`. |
| `twilio-from-number` | Pulled from GitHub Actions secret `TWILIO_FROM_NUMBER` (E.164). |

Container Apps use the [Container Apps secret reference syntax](https://learn.microsoft.com/azure/container-apps/manage-secrets) `secretRef: <secretName>` to expose Key Vault values without baking them into env JSON.

### 7.8 Application Insights + Log Analytics

- Workspace `kb-prod-law-cin`, retention 30 days.
- App Insights `kb-prod-appi-cin` connected to the workspace.
- Connection string injected into both API and worker via env var. Python OpenCensus / OpenTelemetry SDK is wired in `app/main.py` only when `APPLICATIONINSIGHTS_CONNECTION_STRING` is set.

### 7.9 Azure Front Door (`kb-prod-fd`)

- Standard tier. Two origin groups:
  - `web-origin` → `kb-prod-web-cin` Container App FQDN
  - `api-origin` → `kb-prod-api-cin` Container App FQDN
- Routes:
  - `/api/*` → `api-origin`
  - everything else → `web-origin`
- WAF policy in Prevention mode with the OWASP managed rule set.
- Custom domain `khanabazaar.in` + `www.khanabazaar.in` with managed TLS certs.
- Restricts upstream Container Apps via `X-Azure-FDID` header check (Container App ingress IP allowlist).

---

## 8. CI/CD with GitHub Actions

`.github/workflows/deploy.yml` triggers on push to `main`. Pipeline:

1. **Lint + type-check + test** — `ruff`, `mypy`, `pytest` (backend); `npm run lint`, `next build` (frontend).
2. **Login to Azure** — OIDC via `azure/login@v2` using a Workload Identity federated credential (no client secret stored in GitHub).
3. **Build + push images** — `az acr build --registry kbprodacrcin --image khanabazaar-api:$GITHUB_SHA backend/app` (and similarly for worker / web). ACR Tasks does the build cloud-side; runner doesn't need Docker.
4. **Run migrations** — `az containerapp job start --name kb-prod-migrate-cin --resource-group kb-prod-rg --image-name khanabazaar-api:$GITHUB_SHA`. Job blocks until migration exits 0; on non-zero exit, the workflow fails before any revision flips.
5. **Update Container Apps** — `az containerapp update --name <app> --image …:$GITHUB_SHA`. Revision mode is `single`, so each update creates a new revision and shifts 100% traffic once health probes pass. Old revision stays warm for `revisionRetention: 5` revisions.
6. **Smoke test** — `curl https://api.khanabazaar.in/health` must return `{"status":"ok"}`.

Federated credential setup (one-off):

```bash
az ad app create --display-name khanabazaar-gh-deploy
az ad sp create --id <app-id>
az role assignment create --assignee <sp-id> --role Contributor --scope /subscriptions/<sub-id>/resourceGroups/kb-prod-rg
az ad app federated-credential create --id <app-id> --parameters '{
  "name": "github-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:rishimule/KhanaBazaar:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}'
```

---

## 9. Database Migrations

Migrations run as a **Container Apps Job** (`kb-prod-migrate-cin`) — manual trigger type, parallelism 1, replica timeout 600 s.

```bash
az containerapp job start \
  --name kb-prod-migrate-cin \
  --resource-group kb-prod-rg \
  --image kbprodacrcin.azurecr.io/khanabazaar-api:$GITHUB_SHA \
  --env-vars DATABASE_URL=secretref:database-url
# entrypoint inside the image: uv run alembic upgrade head
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
| Roll back                    | `az containerapp revision activate --name kb-prod-api-cin --revision <previous>`.    |
| Pause auto-deploy            | Disable the GitHub Actions workflow (Settings → Actions → Disable workflow).         |
| Hotfix without CI            | `azd deploy --service api` from a developer machine after `azd auth login`.          |

Container Apps keeps the last 5 revisions warm. A rollback is one command — revision metadata + image tag are immutable.

---

## 11. Custom Domain & TLS

1. Delegate `khanabazaar.in` to Azure DNS (NS records at registrar).
2. Front Door → **Domains → Add custom domain** → validate via Azure-managed TXT record. Front Door issues and renews the TLS cert automatically.
3. Update CNAME / ALIAS at apex (`khanabazaar.in`) to the Front Door endpoint.
4. After cert is live, re-deploy the `web` Container App with the production `NEXT_PUBLIC_API_URL=https://api.khanabazaar.in` so the bundle inlines the right URL.
5. Update `FRONTEND_ORIGIN` on the API to the production frontend URL list.

---

## 12. CORS

`backend/app/src/app/__init__.py` currently hardcodes:

```python
allow_origins=[
    "http://localhost:3000",
    "http://127.0.0.1:3000",
],
```

This **blocks production traffic** from `https://khanabazaar.in`. Required change before launch — read `FRONTEND_ORIGIN` (already provisioned in Bicep) and merge it into the allow-list:

1. Add `FRONTEND_ORIGIN: str = ""` to `backend/app/src/app/core/config.py`.
2. In `backend/app/src/app/__init__.py`:
   ```python
   origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
   if settings.FRONTEND_ORIGIN:
       origins.extend(o.strip() for o in settings.FRONTEND_ORIGIN.split(",") if o.strip())
   app.add_middleware(CORSMiddleware, allow_origins=origins, ...)
   ```
3. Set `FRONTEND_ORIGIN` in `azd env` to the comma-separated production origins.

---

## 13. Observability

- **Logs**: Container Apps stream `stdout` + `stderr` to Log Analytics. Query in the Azure Portal → Log Analytics → `ContainerAppConsoleLogs_CL`.
- **App Insights**: Python SDK auto-captures FastAPI requests, dependencies, exceptions. `Live Metrics` blade is the closest equivalent to `tail -f`.
- **CLI tail**: `az containerapp logs show --name kb-prod-api-cin --resource-group kb-prod-rg --follow --tail 200`.
- **Exec into a replica**: `az containerapp exec --name kb-prod-api-cin --resource-group kb-prod-rg --command sh`. Useful for `uv run alembic current`, ad-hoc Python REPL, or `env` checks.

Common issues:

| Symptom                                          | Likely cause / fix                                                              |
|--------------------------------------------------|---------------------------------------------------------------------------------|
| API 500 on every request                         | `DATABASE_URL` driver mismatch — `core/config.py` rewrites `postgres://` to `postgresql+asyncpg://`; confirm the validator runs and Key Vault secret has the right scheme. |
| Migration job exits with `alembic.util.CommandError: Multiple head revisions` | Branch divergence — rebase migration history, generate a merge revision, redeploy. |
| Worker logs `kombu.exceptions.OperationalError` on boot | Redis cold connection retries; usually resolves in <30 s. If persistent, confirm `REDIS_URL` resolves to the private endpoint, not the public FQDN. |
| Frontend hits `localhost:8000` in production     | `NEXT_PUBLIC_API_URL` set after build — re-run the GitHub Actions deploy so `next build` re-inlines the URL. |
| Browser console: CORS error                      | `FRONTEND_ORIGIN` not set, or CORS code still hardcodes localhost — see §12.    |
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

Worker concurrency lives in the Bicep template (Celery `--concurrency 2`); change it there so it's version-controlled, then redeploy.

---

## 15. Cost Expectations

Azure pricing changes; treat the starting tiers as a floor. Approximate monthly cost in `centralindia` at the configured tiers (USD, list price):

- Container Apps (3 apps, Consumption, light load): ~$15–30
- Postgres Burstable B1ms: ~$15
- Azure Cache for Redis Basic C0: ~$16
- ACR Basic: ~$5
- Key Vault, Log Analytics, App Insights: ~$5–10 with low log volume
- Azure Front Door Standard: ~$35 base + traffic
- Azure DNS: ~$1

Total at idle: ~$90–110/month. Use the [Azure pricing calculator](https://azure.microsoft.com/pricing/calculator/) for accurate estimates and watch the cost analysis blade weekly.

---

## 16. Disaster Recovery

- **Postgres backups**: 7-day retention, geo-redundant. Restore via Portal → Postgres server → **Restore**, choose point-in-time (UTC). Restore creates a new server; repoint Key Vault `database-url` and redeploy.
- **Manual backup**: from Cloud Shell or any VNet-connected runner:
  ```bash
  pg_dump "host=kb-prod-pg-cin.postgres.database.azure.com user=kbadmin dbname=khanabazaar sslmode=require" > kb-prod-backup-$(date +%F).sql
  ```
  Pipe to a storage account in `kb-network-rg` for off-cluster retention.
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
