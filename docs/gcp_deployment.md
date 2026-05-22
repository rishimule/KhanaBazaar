<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Google Cloud Platform Deployment Guide

Production deployment plan for Khana Bazaar on Google Cloud Platform. Target profile: **MVP / low traffic, lowest cost**, single region **Mumbai (`asia-south1`)**. Stack favours managed serverless (Cloud Run + Cloud SQL + Memorystore) over GKE — no kubelet babysitting, no VM patching except for one tiny Redis bastion if you choose the cheaper Redis option.

> **Status:** target architecture, parallel to `docs/azure_deployment.md`. None of these GCP resources are provisioned yet. None of the Dockerfiles, Terraform, or GitHub Actions referenced below are committed. Treat this document as the implementation spec.

---

## 1. Service Map

| Khana Bazaar component | GCP service | Tier (MVP starting point) |
|---|---|---|
| FastAPI backend (`khanabazaar-api`) | Cloud Run (HTTP) | 1 vCPU / 512 MiB, min=0, max=5 |
| Celery worker (`khanabazaar-worker`) | Cloud Run (no ingress, CPU always-allocated) | 1 vCPU / 512 MiB, min=1, max=2 |
| Celery beat scheduler (`khanabazaar-beat`) | Cloud Run (no ingress, CPU always-allocated) | 0.25 vCPU / 256 MiB, min=1, max=1 |
| Next.js frontend (`khanabazaar-web`) | Cloud Run (HTTP) | 1 vCPU / 512 MiB, min=0, max=5 |
| Meilisearch v1.11 | Cloud Run + GCS Fuse mount (`/meili_data`) | 1 vCPU / 2 GiB, min=1, max=1, CPU always-allocated |
| PostgreSQL 15 + PostGIS | Cloud SQL for PostgreSQL | `db-f1-micro` (1 shared vCPU / 0.6 GiB) + 10 GiB SSD |
| Redis 7 | **Option A (default):** Memorystore for Redis, Basic 1 GiB. **Option B (cheaper):** `e2-micro` Compute Engine VM running Redis | A: ~$35/mo. B: ~$7/mo |
| Container images | Artifact Registry (Docker repo) | Standard |
| Secrets (JWT, OTP pepper, Resend, DB, Meili key) | Secret Manager | Standard |
| Object storage (Meili data, future media) | Cloud Storage (GCS) | Standard, regional |
| Logs / metrics / traces | Cloud Logging + Cloud Monitoring | Free tier covers MVP |
| Custom domain + TLS | Cloud Run domain mapping (managed certs) | Free |
| DNS | Cloud DNS (or external — Cloudflare, Namecheap) | $0.20/zone/mo if on Cloud DNS |
| Identity for CI/CD | Workload Identity Federation (OIDC from GitHub Actions) | Free |
| Egress / NAT | Direct VPC egress on Cloud Run (preview, free) or Serverless VPC Connector ($) | See §6 |

All resources live in **`asia-south1` (Mumbai)**. No multi-region failover at MVP — Cloud SQL automated backups + a daily Meili snapshot to GCS cover DR.

---

## 2. Topology

```
                            ┌──────────────────────────┐
                            │  Cloud Run domain map    │  TLS, custom hostname
                            │  khanabazaar.in          │
                            └──────────┬───────────────┘
                                       │ HTTPS
                            ┌──────────▼───────────────┐
                            │  Cloud Run: web (Next.js)│  public ingress
                            └──────────┬───────────────┘
                                       │ same-origin /api/v1/* rewrite
                            ┌──────────▼───────────────┐
                            │  Cloud Run: api (FastAPI)│  public ingress (or internal-only behind LB)
                            └──┬───────┬───────┬───────┘
                               │       │       │
              ┌────────────────┘       │       └────────────────┐
              │ asyncpg                │ Redis (broker+cache)    │ Meili HTTP
   ┌──────────▼───────────┐  ┌─────────▼──────────┐  ┌───────────▼──────────────┐
   │ Cloud SQL Postgres15 │  │ Memorystore Redis  │  │ Cloud Run: meilisearch   │
   │ + PostGIS extension  │  │ Basic 1 GiB        │  │ + GCS Fuse → kb-meili-* │
   └──────────────────────┘  └─────────┬──────────┘  └──────────────────────────┘
                                       │
                            ┌──────────▼───────────────┐
                            │  Cloud Run: worker       │  Celery consumer, min=1
                            │  Cloud Run: beat         │  Celery scheduler, min=1
                            └──────────────────────────┘
```

Private networking notes:

- Cloud SQL: **Private IP** only, reachable from Cloud Run via direct VPC egress (or Serverless VPC Connector if direct egress is not yet GA in `asia-south1`).
- Memorystore: VPC-internal only. Same VPC egress path as Cloud SQL.
- Meili Cloud Run service: `--ingress=internal`. The `api` and `worker` services hit it over its `*.run.app` URL, gated by IAM-authenticated invocation.

---

## 3. Cost Estimate (MVP, asia-south1, INR ≈ $1 = ₹83)

| Item | Monthly USD (idle) | Monthly USD (light traffic) |
|---|---:|---:|
| Cloud Run api (min=0) | $0 | $5 |
| Cloud Run web (min=0) | $0 | $5 |
| Cloud Run worker (min=1, CPU always-allocated) | $10 | $12 |
| Cloud Run beat (min=1, 0.25 vCPU) | $4 | $4 |
| Cloud Run meilisearch (min=1) | $20 | $22 |
| Cloud SQL `db-f1-micro` + 10 GiB SSD | $10 | $10 |
| Memorystore Redis Basic 1 GiB (Option A) | $35 | $35 |
| **OR** Compute Engine `e2-micro` + Redis (Option B) | $7 | $7 |
| Artifact Registry storage (~2 GiB) | $0.10 | $0.10 |
| Cloud Logging / Monitoring (free tier) | $0 | $0 |
| Cloud Storage (meili snapshots, ~5 GiB) | $0.10 | $0.10 |
| Secret Manager (6 secrets, light reads) | $0.30 | $0.30 |
| Egress to internet (~1 GiB) | $0.12 | $0.12 |
| **Total — Option A** | **~$80** | **~$95** |
| **Total — Option B** | **~$52** | **~$67** |

Real bills depend on traffic, image-pull egress, and idle vs warm Cloud Run revisions. Set a **billing budget alert at ₹6,500 / $80** under `Billing → Budgets & alerts` before anything else.

---

## 4. Prerequisites

```bash
# Tools (host machine)
gcloud --version           # ≥ 500.0.0
docker --version           # for local build/push if you do not use Cloud Build
git --version
```

A GCP organisation is not required; a personal billing account on a single project is fine. Pick a project ID — e.g. `kb-prod` — that you do not plan to rename. Project IDs are immutable.

```bash
gcloud auth login
gcloud projects create kb-prod --name="Khana Bazaar Prod"
gcloud config set project kb-prod
gcloud beta billing projects link kb-prod --billing-account=XXXX-XXXX-XXXX
```

Enable APIs (one-time, can take a few minutes):

```bash
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  vpcaccess.googleapis.com \
  servicenetworking.googleapis.com \
  compute.googleapis.com \
  cloudresourcemanager.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com
```

---

## 5. Project layout — what you will add to the repo

```
backend/app/
  Dockerfile                # FastAPI image (uvicorn entrypoint)
  Dockerfile.worker         # same image; CMD overridden in Cloud Run
frontend/
  Dockerfile                # next build → next start
deploy/
  gcp/
    cloudrun-api.yaml       # Cloud Run service manifest
    cloudrun-worker.yaml
    cloudrun-beat.yaml
    cloudrun-web.yaml
    cloudrun-meili.yaml
    redis-vm-startup.sh     # Option B: cloud-init for Redis VM
.github/workflows/
  deploy.yml                # build → push → deploy on push to main
```

You do not need Terraform for MVP. Everything below uses raw `gcloud` calls; commit them as a shell script under `deploy/gcp/bootstrap.sh` once you have run them once and confirmed they work.

---

## 6. Networking

Create a custom VPC so Cloud SQL and Memorystore have private IPs:

```bash
REGION=asia-south1

gcloud compute networks create kb-vpc \
  --subnet-mode=custom

gcloud compute networks subnets create kb-subnet \
  --network=kb-vpc \
  --region=$REGION \
  --range=10.10.0.0/20
```

Reserve a `/24` for Google-managed services (Cloud SQL private IP):

```bash
gcloud compute addresses create google-managed-services-kb-vpc \
  --global \
  --purpose=VPC_PEERING \
  --prefix-length=24 \
  --network=kb-vpc

gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges=google-managed-services-kb-vpc \
  --network=kb-vpc
```

**Cloud Run → VPC egress.** Two options:

1. **Direct VPC egress (recommended where available — GA in `asia-south1` as of late 2025).** No connector to pay for; configure per-service with `--network=kb-vpc --subnet=kb-subnet --vpc-egress=private-ranges-only`.
2. **Serverless VPC Connector** (fallback). Costs ~$10/mo for the smallest tier:

   ```bash
   gcloud compute networks vpc-access connectors create kb-connector \
     --region=$REGION \
     --network=kb-vpc \
     --range=10.8.0.0/28 \
     --min-instances=2 --max-instances=3 \
     --machine-type=f1-micro
   ```

Use direct VPC egress unless the deploy fails with "feature not available".

---

## 7. Cloud SQL — Postgres 15 + PostGIS

```bash
gcloud sql instances create kb-pg \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=$REGION \
  --storage-size=10GB \
  --storage-type=SSD \
  --network=projects/kb-prod/global/networks/kb-vpc \
  --no-assign-ip \
  --backup-start-time=18:00 \
  --enable-point-in-time-recovery \
  --availability-type=ZONAL
```

`--no-assign-ip` makes the instance private-only. Backups + PITR are cheap and worth turning on from day one.

Create the app database, user, and PostGIS extension:

```bash
gcloud sql databases create khanabazaar --instance=kb-pg

# Strong password; store immediately in Secret Manager (see §9)
gcloud sql users create kb_app --instance=kb-pg --password='REPLACE_ME'

# Enable PostGIS — connect via the proxy from your laptop once
gcloud sql connect kb-pg --user=postgres --database=khanabazaar
# At the psql prompt:
# CREATE EXTENSION IF NOT EXISTS postgis;
# CREATE EXTENSION IF NOT EXISTS postgis_topology;
# \q
```

The app's PostGIS-generated `geo` column (see `CLAUDE.md`) requires this extension to be present **before** `alembic upgrade head`.

Connection string for the app:

```
postgresql+asyncpg://kb_app:<PASSWORD>@<PRIVATE_IP>:5432/khanabazaar
```

Find `<PRIVATE_IP>` via `gcloud sql instances describe kb-pg --format='value(ipAddresses[0].ipAddress)'`.

---

## 8. Redis — pick A or B

### Option A — Memorystore (managed, ~$35/mo)

```bash
gcloud redis instances create kb-redis \
  --size=1 \
  --region=$REGION \
  --tier=BASIC \
  --redis-version=redis_7_2 \
  --network=projects/kb-prod/global/networks/kb-vpc \
  --connect-mode=PRIVATE_SERVICE_ACCESS
```

Connection: `redis://<PRIVATE_IP>:6379/0`. No password by default (network-isolated). Note: Memorystore Basic is **not** highly available — accept this for MVP, or move to Standard tier later (~$70/mo).

### Option B — Redis on `e2-micro` Compute Engine (~$7/mo)

Cheaper but you own patching. `deploy/gcp/redis-vm-startup.sh`:

```bash
#!/usr/bin/env bash
apt-get update
apt-get install -y redis-server
sed -i 's/^bind .*/bind 0.0.0.0/' /etc/redis/redis.conf
sed -i 's/^protected-mode yes/protected-mode no/' /etc/redis/redis.conf
sed -i 's/^# maxmemory <bytes>/maxmemory 512mb/' /etc/redis/redis.conf
sed -i 's/^# maxmemory-policy noeviction/maxmemory-policy allkeys-lru/' /etc/redis/redis.conf
systemctl enable redis-server
systemctl restart redis-server
```

```bash
gcloud compute instances create kb-redis-vm \
  --machine-type=e2-micro \
  --zone=asia-south1-a \
  --image-family=debian-12 --image-project=debian-cloud \
  --network=kb-vpc --subnet=kb-subnet \
  --no-address \
  --metadata-from-file=startup-script=deploy/gcp/redis-vm-startup.sh \
  --tags=redis
```

Firewall — allow Redis from Cloud Run direct VPC egress range and the VPC connector range only:

```bash
gcloud compute firewall-rules create allow-redis-internal \
  --network=kb-vpc \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:6379 \
  --source-ranges=10.10.0.0/20,10.8.0.0/28 \
  --target-tags=redis
```

Connection: `redis://<INTERNAL_IP>:6379/0`. Snapshot the VM weekly: `gcloud compute disks snapshot kb-redis-vm --zone=asia-south1-a`.

---

## 9. Secret Manager

Create one secret per credential. Versions are immutable — rotate by adding a new version.

```bash
echo -n "$(openssl rand -hex 32)" | gcloud secrets create jwt-secret --data-file=-
echo -n "$(openssl rand -hex 32)" | gcloud secrets create otp-pepper --data-file=-
echo -n "REPLACE_ME"              | gcloud secrets create db-password --data-file=-
echo -n "REPLACE_ME"              | gcloud secrets create resend-api-key --data-file=-
echo -n "$(openssl rand -hex 32)" | gcloud secrets create meili-master-key --data-file=-
echo -n "REPLACE_ME"              | gcloud secrets create gmaps-server-key --data-file=-
echo -n "REPLACE_ME"              | gcloud secrets create gmaps-browser-key --data-file=-
```

The Cloud Run runtime service account (created in §11) needs `roles/secretmanager.secretAccessor` on each secret.

---

## 10. Container images

### Artifact Registry

```bash
gcloud artifacts repositories create kb \
  --location=$REGION \
  --repository-format=docker
gcloud auth configure-docker asia-south1-docker.pkg.dev
```

Image URIs: `asia-south1-docker.pkg.dev/kb-prod/kb/<service>:<git-sha>`.

### `backend/app/Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src"

# Cloud Run injects $PORT (default 8080). Bind there.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

### `backend/app/Dockerfile.worker`

Single image is enough — the worker reuses the api image and overrides `CMD`. Skip a separate Dockerfile and pass `--command` / `--args` to Cloud Run instead. Documented here for clarity:

```bash
# worker entrypoint set on the Cloud Run service, not in the image
celery -A app.core.celery_app worker --loglevel=info --concurrency=2

# beat entrypoint
celery -A app.core.celery_app beat --loglevel=info
```

### `frontend/Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
ARG NEXT_PUBLIC_API_URL=""
ARG NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY=""
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY=$NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.ts ./next.config.ts

CMD ["sh", "-c", "npm start -- --port ${PORT:-8080} --hostname 0.0.0.0"]
```

`NEXT_PUBLIC_*` is inlined at build time — pass the production API URL as a `--build-arg` in CI.

`next.config.ts` rewrites `/api/v1/*` to `http://localhost:8000` for local dev. In production the rewrite must point at the api Cloud Run URL. Add a runtime branch:

```ts
// next.config.ts
const API_TARGET = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
// then use `${API_TARGET}/api/v1/:rest`
```

Set `API_INTERNAL_URL` on the web Cloud Run service to the api service's `*.run.app` URL.

---

## 11. Cloud Run — services

Two service accounts, principle of least privilege:

```bash
gcloud iam service-accounts create kb-runtime
gcloud iam service-accounts create kb-deployer
```

Grant `kb-runtime` what the apps need at runtime:

```bash
SA=kb-runtime@kb-prod.iam.gserviceaccount.com

gcloud projects add-iam-policy-binding kb-prod \
  --member="serviceAccount:$SA" --role=roles/cloudsql.client
gcloud projects add-iam-policy-binding kb-prod \
  --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor
gcloud projects add-iam-policy-binding kb-prod \
  --member="serviceAccount:$SA" --role=roles/logging.logWriter
gcloud projects add-iam-policy-binding kb-prod \
  --member="serviceAccount:$SA" --role=roles/monitoring.metricWriter
# Meili service needs GCS access for the Fuse mount
gcloud projects add-iam-policy-binding kb-prod \
  --member="serviceAccount:$SA" --role=roles/storage.objectUser
```

### 11a. `khanabazaar-api`

```bash
gcloud run deploy khanabazaar-api \
  --region=$REGION \
  --image=asia-south1-docker.pkg.dev/kb-prod/kb/api:$GIT_SHA \
  --service-account=$SA \
  --network=kb-vpc --subnet=kb-subnet --vpc-egress=private-ranges-only \
  --cpu=1 --memory=512Mi \
  --min-instances=0 --max-instances=5 --concurrency=40 \
  --port=8080 \
  --allow-unauthenticated \
  --set-env-vars="ENVIRONMENT=production" \
  --set-env-vars="API_V1_STR=/api/v1" \
  --set-env-vars="FRONTEND_ORIGIN=https://khanabazaar.in,https://www.khanabazaar.in" \
  --set-env-vars="MEILI_URL=https://khanabazaar-meili-xxxx-el.a.run.app" \
  --set-env-vars="EMAIL_PROVIDER=resend" \
  --set-env-vars="RESEND_FROM_EMAIL=no-reply@khanabazaar.in" \
  --set-env-vars="SUPPORT_EMAIL=support@khanabazaar.in" \
  --set-env-vars="SMS_PROVIDER=console" \
  --set-secrets="JWT_SECRET=jwt-secret:latest" \
  --set-secrets="OTP_PEPPER=otp-pepper:latest" \
  --set-secrets="RESEND_API_KEY=resend-api-key:latest" \
  --set-secrets="MEILI_MASTER_KEY=meili-master-key:latest" \
  --set-secrets="GOOGLE_MAPS_SERVER_API_KEY=gmaps-server-key:latest" \
  --set-env-vars="DATABASE_URL=postgresql+asyncpg://kb_app:$(...password...)@<PG_PRIVATE_IP>:5432/khanabazaar" \
  --set-env-vars="REDIS_URL=redis://<REDIS_PRIVATE_IP>:6379/0"
```

For `DATABASE_URL` it is cleaner to store the entire DSN (with password) as one secret and bind it via `--set-secrets="DATABASE_URL=database-url:latest"`. Same with `REDIS_URL`.

### 11b. `khanabazaar-worker`

Same image, different command, no ingress:

```bash
gcloud run deploy khanabazaar-worker \
  --region=$REGION \
  --image=asia-south1-docker.pkg.dev/kb-prod/kb/api:$GIT_SHA \
  --service-account=$SA \
  --network=kb-vpc --subnet=kb-subnet --vpc-egress=private-ranges-only \
  --cpu=1 --memory=512Mi --cpu-boost \
  --no-cpu-throttling \
  --min-instances=1 --max-instances=2 \
  --no-allow-unauthenticated \
  --ingress=internal \
  --command="celery" \
  --args="-A,app.core.celery_app,worker,--loglevel=info,--concurrency=2" \
  --set-env-vars="...same as api..." \
  --set-secrets="...same as api..."
```

`--no-cpu-throttling` is critical — Celery workers must process tasks between HTTP requests. Without it, Cloud Run idles the CPU and the worker stops draining the queue.

### 11c. `khanabazaar-beat`

```bash
gcloud run deploy khanabazaar-beat \
  --region=$REGION \
  --image=asia-south1-docker.pkg.dev/kb-prod/kb/api:$GIT_SHA \
  --service-account=$SA \
  --network=kb-vpc --subnet=kb-subnet --vpc-egress=private-ranges-only \
  --cpu=0.25 --memory=256Mi \
  --no-cpu-throttling \
  --min-instances=1 --max-instances=1 \
  --no-allow-unauthenticated \
  --ingress=internal \
  --command="celery" \
  --args="-A,app.core.celery_app,beat,--loglevel=info" \
  --set-env-vars="...same as api..." \
  --set-secrets="...same as api..."
```

Beat **must** be a singleton — `max-instances=1`. If you ever bump it, you will get duplicate scheduled tasks.

### 11d. `khanabazaar-web`

```bash
gcloud run deploy khanabazaar-web \
  --region=$REGION \
  --image=asia-south1-docker.pkg.dev/kb-prod/kb/web:$GIT_SHA \
  --service-account=$SA \
  --cpu=1 --memory=512Mi \
  --min-instances=0 --max-instances=5 --concurrency=80 \
  --port=8080 \
  --allow-unauthenticated \
  --set-env-vars="API_INTERNAL_URL=https://khanabazaar-api-xxxx-el.a.run.app"
```

Frontend does not need VPC egress unless you proxy directly to private Redis/PG (you don't).

### 11e. `khanabazaar-meili`

Provision a GCS bucket for the data dir:

```bash
gcloud storage buckets create gs://kb-meili-data --location=$REGION --uniform-bucket-level-access
```

Cloud Run with GCS Fuse mount (GA as of 2025):

```bash
gcloud run deploy khanabazaar-meili \
  --region=$REGION \
  --image=getmeili/meilisearch:v1.11 \
  --service-account=$SA \
  --cpu=1 --memory=2Gi \
  --no-cpu-throttling \
  --min-instances=1 --max-instances=1 --concurrency=80 \
  --port=7700 \
  --no-allow-unauthenticated \
  --ingress=internal \
  --add-volume=name=meili-data,type=cloud-storage,bucket=kb-meili-data \
  --add-volume-mount=volume=meili-data,mount-path=/meili_data \
  --set-env-vars="MEILI_ENV=production" \
  --set-env-vars="MEILI_NO_ANALYTICS=true" \
  --set-secrets="MEILI_MASTER_KEY=meili-master-key:latest"
```

Meili is single-writer — never raise `max-instances` above 1. Grant the api + worker service account `roles/run.invoker` on the meili service:

```bash
gcloud run services add-iam-policy-binding khanabazaar-meili \
  --region=$REGION \
  --member="serviceAccount:$SA" \
  --role="roles/run.invoker"
```

The api/worker calls Meili with an `Authorization: Bearer $(gcloud auth print-identity-token)` header. The `meilisearch-python-sdk` accepts a custom request transport — wire one up that prepends a GCP identity token before every call. See `app/search/client.py` (to be added; mirror the pattern from `core/email.py` where the Resend dispatcher injects a per-request Bearer header).

---

## 12. Custom domain + TLS

Free, no LB required.

```bash
gcloud beta run domain-mappings create \
  --region=$REGION \
  --service=khanabazaar-web \
  --domain=khanabazaar.in

gcloud beta run domain-mappings create \
  --region=$REGION \
  --service=khanabazaar-web \
  --domain=www.khanabazaar.in
```

Then add the `A` / `AAAA` / `CNAME` records GCP returns at your DNS provider. Managed certs are issued automatically.

For `api.khanabazaar.in` you can either:
- Map it to `khanabazaar-api` directly, **or**
- Skip the public api hostname entirely; let the web service proxy `/api/v1/*` through the Next.js rewrite. Recommended — fewer DNS records, no CORS, smaller attack surface. This matches how local dev works (`docs/local_setup.md` §6a).

---

## 13. CI/CD — GitHub Actions + Workload Identity Federation

No long-lived JSON keys. OIDC from GitHub Actions → short-lived GCP token.

### 13a. One-time WIF setup

```bash
PROJECT_NUMBER=$(gcloud projects describe kb-prod --format='value(projectNumber)')
GH_REPO="rishimule/KhanaBazaar"   # change to your repo

gcloud iam workload-identity-pools create gh-pool \
  --location=global --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc gh-provider \
  --location=global --workload-identity-pool=gh-pool \
  --display-name="GitHub OIDC" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='$GH_REPO'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

gcloud iam service-accounts add-iam-policy-binding \
  kb-deployer@kb-prod.iam.gserviceaccount.com \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/gh-pool/attribute.repository/$GH_REPO"

# Deploy permissions
for ROLE in run.admin artifactregistry.writer iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding kb-prod \
    --member="serviceAccount:kb-deployer@kb-prod.iam.gserviceaccount.com" \
    --role="roles/$ROLE"
done
```

Repository secrets to set in GitHub:

| Secret | Value |
|---|---|
| `GCP_PROJECT_ID` | `kb-prod` |
| `GCP_PROJECT_NUMBER` | output of `projects describe` |
| `GCP_WIF_PROVIDER` | `projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/gh-pool/providers/gh-provider` |
| `GCP_DEPLOYER_SA` | `kb-deployer@kb-prod.iam.gserviceaccount.com` |
| `GCP_REGION` | `asia-south1` |

### 13b. `.github/workflows/deploy.yml`

```yaml
name: deploy
on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  id-token: write   # required for WIF

env:
  REGION: ${{ secrets.GCP_REGION }}
  PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
  AR_HOST: ${{ secrets.GCP_REGION }}-docker.pkg.dev

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - id: auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WIF_PROVIDER }}
          service_account: ${{ secrets.GCP_DEPLOYER_SA }}

      - uses: google-github-actions/setup-gcloud@v2
      - run: gcloud auth configure-docker $AR_HOST --quiet

      - name: Build & push api image
        run: |
          IMG=$AR_HOST/$PROJECT_ID/kb/api:${{ github.sha }}
          docker build -t $IMG -f backend/app/Dockerfile backend/app
          docker push $IMG
          echo "API_IMAGE=$IMG" >> $GITHUB_ENV

      - name: Build & push web image
        run: |
          IMG=$AR_HOST/$PROJECT_ID/kb/web:${{ github.sha }}
          docker build -t $IMG \
            --build-arg NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY=${{ secrets.NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY }} \
            -f frontend/Dockerfile frontend
          docker push $IMG
          echo "WEB_IMAGE=$IMG" >> $GITHUB_ENV

      - name: Deploy api
        run: gcloud run services update khanabazaar-api --region=$REGION --image=$API_IMAGE

      - name: Deploy worker
        run: gcloud run services update khanabazaar-worker --region=$REGION --image=$API_IMAGE

      - name: Deploy beat
        run: gcloud run services update khanabazaar-beat --region=$REGION --image=$API_IMAGE

      - name: Deploy web
        run: gcloud run services update khanabazaar-web --region=$REGION --image=$WEB_IMAGE
```

`gcloud run services update --image` keeps every other flag (env, secrets, scaling) at whatever was last set by `gcloud run deploy`. Use `deploy` only for first-time bring-up or when changing flags; use `update --image` for the steady-state release.

---

## 14. First-deploy runbook

Order matters because the api boot path runs `app.search.bootstrap` which expects Meili reachable, and Celery beat expects Redis reachable.

1. **Provision infra** — VPC, Cloud SQL (+ `CREATE EXTENSION postgis`), Redis (Memorystore or VM), GCS bucket, secrets, Artifact Registry, service accounts. (§4–§10)
2. **Push images** — locally once, just to get something in Artifact Registry:
   ```bash
   docker build -t $AR_HOST/$PROJECT_ID/kb/api:bootstrap -f backend/app/Dockerfile backend/app
   docker push $AR_HOST/$PROJECT_ID/kb/api:bootstrap
   docker build -t $AR_HOST/$PROJECT_ID/kb/web:bootstrap -f frontend/Dockerfile frontend
   docker push $AR_HOST/$PROJECT_ID/kb/web:bootstrap
   ```
3. **Deploy Meili first** (§11e). Smoke: `curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" https://khanabazaar-meili-…/health`.
4. **Run Alembic migrations** as a one-shot Cloud Run job:
   ```bash
   gcloud run jobs create kb-migrate \
     --region=$REGION \
     --image=$AR_HOST/$PROJECT_ID/kb/api:bootstrap \
     --service-account=$SA \
     --network=kb-vpc --subnet=kb-subnet --vpc-egress=private-ranges-only \
     --set-secrets="DATABASE_URL=database-url:latest" \
     --command="alembic" --args="upgrade,head"
   gcloud run jobs execute kb-migrate --region=$REGION --wait
   ```
5. **Deploy api → worker → beat → web** (§11a–d).
6. **Seed Meili indexes** via one-shot exec into the api container:
   ```bash
   gcloud run jobs create kb-reindex \
     --region=$REGION \
     --image=$AR_HOST/$PROJECT_ID/kb/api:bootstrap \
     --service-account=$SA \
     --network=kb-vpc --subnet=kb-subnet --vpc-egress=private-ranges-only \
     --set-env-vars="..." --set-secrets="..." \
     --command="python" --args="-m,app.search.reindex,--all"
   gcloud run jobs execute kb-reindex --region=$REGION --wait
   ```
7. **Smoke test** the public endpoints:
   ```bash
   curl https://khanabazaar.in/                                       # web 200
   curl https://khanabazaar.in/api/v1/meta/health                     # {"status":"ok"}
   curl 'https://khanabazaar.in/api/v1/search/suggest?q=milk'         # results
   ```
8. **Verify Celery** — request an OTP. Check the worker logs in Cloud Logging for the email task.
9. **Create the first admin user** through whatever bootstrap script you already have (see `backend/app/src/app/db/seed*` scripts). Custom step — there is no admin-self-signup.

---

## 15. Observability

Cloud Run pushes stdout / stderr to Cloud Logging automatically. Filter by service:

```
resource.type="cloud_run_revision"
resource.labels.service_name="khanabazaar-api"
severity>=WARNING
```

Useful saved searches in Cloud Logging:

- **OTP failures**: `jsonPayload.event="otp.verify.fail"`
- **Order writes**: `jsonPayload.event=~"order\\."`
- **Meili sync**: `resource.labels.service_name="khanabazaar-worker" jsonPayload.event=~"search\\."`

Set up alerting policies in Cloud Monitoring for:

- Cloud Run 5xx rate > 1% over 5 min (api + web)
- Cloud SQL CPU > 80% sustained 10 min
- Memorystore memory > 90%
- Celery queue depth (custom metric — emit from worker via `monitoring_v3` once tasks back up)

App tracing / structured request logs: not wired yet. `docs/azure_deployment.md` §13 lists this as a launch blocker on the Azure side; the GCP equivalent is OpenTelemetry → Cloud Trace via `opentelemetry-exporter-gcp-trace`. Add when traffic justifies.

---

## 16. Backups & DR

- **Cloud SQL**: automated daily backups + PITR enabled in §7. Retains 7 days by default; bump to 30 in `gcloud sql instances patch kb-pg --backup-retention-days=30 --transaction-log-retention-days=7`.
- **Meili**: nightly `meilisearch-dumper` Cloud Run job → `gs://kb-meili-data/dumps/YYYY-MM-DD.dump`. Restore by deleting Meili's Cloud Run service, re-creating it with the dump pre-staged in the bucket, and running `--import-dump` on first boot.
- **GCS**: object versioning on `kb-meili-data` (`gcloud storage buckets update gs://kb-meili-data --versioning`).
- **Secret Manager**: versions are immutable; rotation = new version. Pin Cloud Run to `:latest` so rotation is a no-redeploy event (Cloud Run picks up new versions on the next cold start, within ~60s).

DR scenario — full project loss:
1. New project, re-run §4 → §10.
2. Restore Cloud SQL from latest backup (`gcloud sql backups restore`).
3. Re-import Meili dump.
4. Re-push images, re-deploy Cloud Run services.

ETA ~2 hours assuming images are still in another registry. Cheaper than running a warm DR region.

---

## 17. Cost-saving toggles

Things to flip **only after MVP traffic is observed**:

1. **Memorystore → VM Redis** if Memorystore exceeds 20% of bill and HA does not matter yet (Option B in §8).
2. **Scale-to-zero the worker**: replace Celery with Cloud Tasks + Cloud Run HTTP handler. Requires moving every `@celery_app.task` into an HTTP endpoint and emitting tasks via the Cloud Tasks SDK. Saves the always-on worker cost (~$12/mo). Out of scope for this guide; revisit when worker idle time exceeds 70%.
3. **Cloud SQL committed-use discount**: 1-year CUD on `db-f1-micro` saves ~25%. Worth it once the workload is stable.
4. **Cloud Run min-instances=0 on api** — already default. If cold starts hurt (>2s p95), set min=1 and accept the ~$10/mo.
5. **Egress**: 1 GiB free per month from `asia-south1` to internet (as of 2025 pricing). Heavy image traffic blows past this fast — move static images to GCS + Cloud CDN before traffic scales.

---

## 18. Known gaps vs `azure_deployment.md`

Parity not yet reached on the GCP side:

- **App Insights / OpenTelemetry**: not wired in either deployment. Same launch-blocker as Azure.
- **WAF**: Azure plan uses Front Door Premium. GCP equivalent is Cloud Armor in front of an external HTTPS load balancer, which costs ~$18/mo for the LB alone. Skipped at MVP; Cloud Run's built-in DDoS protection is acceptable until traffic justifies the LB spend.
- **CDN**: same — no Cloud CDN at MVP. Add behind an HTTPS LB once image traffic exceeds the egress free tier.
- **Multi-region failover**: not in scope at MVP. Cloud SQL backup + Meili dump = 2-hour RTO from any region.
- **Mobile testing tunnel**: `scripts/dev.sh start --tunnel` (ngrok) keeps working unchanged — it is a local-dev concern.

---

## 19. Tear-down

If you abandon GCP, kill the bill in one shot:

```bash
gcloud projects delete kb-prod
```

Project deletion is reversible for 30 days. Past that, every resource (including the Cloud SQL backups) is gone. Export anything you want before deleting.
