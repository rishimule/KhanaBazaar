<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Google Cloud Platform Deployment

**Status: LIVE.** Khana Bazaar's MVP runs on GCP — project `khanabazaar-mvp`,
single region **Mumbai (`asia-south1`)**, optimized for low cost on ~$290 of
free credits (~$49/mo → ~6 months).

This document is the **architecture overview** (what runs where, and why). For
the exact provisioning + redeploy commands, see the runbook
[`../deploy/gcp/README.md`](../deploy/gcp/README.md).

## Service map

| Component | Where it runs | Sizing |
|---|---|---|
| `khanabazaar-web` (Next.js) | Cloud Run | 1 vCPU / 1 GiB, **min=1** (always-warm), max=2 |
| `khanabazaar-api` (FastAPI) | Cloud Run | 1 vCPU / 1 GiB, **min=1** (always-warm), max=3 |
| Celery worker **+ embedded beat** | container on the VM | shares the VM |
| Redis 7 (broker + cache) | container on the VM | requirepass, internal-IP bind |
| Meilisearch v1.11 | container on the VM | persistent disk at `/mnt/disks/meili` |
| cloud-sql-proxy | container on the VM | localhost:5432 for the worker |
| PostgreSQL 15 + PostGIS | Cloud SQL | `db-f1-micro`, 10 GiB SSD, public IP **with zero authorized networks** (connector-only) |
| Container images | Artifact Registry | `asia-south1-docker.pkg.dev/khanabazaar-mvp/kb` |
| Secrets | Secret Manager | JWT, OTP pepper, DB URL, Redis URL, Meili key, VAPID, Maps server key, dev-inbox password |
| Custom domain | Firebase Hosting (free) | `khanabazaar.rishimule.dev` → rewrites to `khanabazaar-web` |

**Why a VM for worker/redis/meili instead of more Cloud Run services:** a Cloud
Run Celery worker needs "CPU always allocated" (~$45–65/mo for one instance);
co-locating worker + beat + Redis + Meilisearch on a single **e2-small VM**
(`kb-svc`) is far cheaper and removes the http-sidecar startup-probe hack. Cloud
Run reaches the VM's internal IP over **Direct VPC egress** (cheaper than a
Serverless VPC connector). Cloud SQL is reached by Cloud Run via the Cloud SQL
connector socket, and by the VM worker via the local cloud-sql-proxy.

## Topology

```
                         Firebase Hosting (free, managed TLS, CDN)
   Browser ─khanabazaar.rishimule.dev─▶  rewrite "**" → khanabazaar-web
        │                                                   │
        └─────────── *.run.app ─────────────────────────────┤
                                                             ▼
                   ┌──────────── Cloud Run (asia-south1, min=1) ───────────┐
                   │  web (Next.js)  ──server-side /api/v1 proxy──▶  api     │
                   └──────────┬──────────────────────────────┬─────────────┘
                              │ Cloud SQL connector           │ Direct VPC egress
                              ▼                               ▼
                      Cloud SQL PG15+PostGIS         e2-small VM "kb-svc" (VPC)
                                                     ├─ redis (requirepass)
                                                     ├─ meilisearch (disk)
                                                     ├─ cloud-sql-proxy
                                                     └─ celery worker + beat
```

## CI/CD

Merge to `main` → `.github/workflows/deploy.yml` (GitHub Actions authenticated to
GCP via **Workload Identity Federation** — no JSON key). The pipeline builds +
pushes the api and web images, runs the `kb-migrate` Cloud Run Job (alembic
migrate → idempotent seed → Meilisearch reindex), `gcloud run deploy`s api + web,
and restarts the worker on the VM via `gcloud compute ssh --tunnel-through-iap`.

## Email / SMS (MVP)

No Resend/Twilio yet. The deploy runs with `ENVIRONMENT=development`,
`EMAIL_PROVIDER=console`, `SMS_PROVIDER=console`, so all outbound email + SMS
(including login OTPs) are captured in the **dev-mailbox** — readable at
`/dev-emails` and `/dev-sms` behind HTTP Basic auth (`DEV_INBOX_USER` /
`DEV_INBOX_PASSWORD`). This is a demo posture, not a production launch.

## Cost

~$49/mo: Cloud Run web+api always-warm (~$20), e2-small VM + disks (~$15),
Cloud SQL db-f1-micro (~$11), Artifact Registry + egress (~$3). A billing budget
alerts at 20000 INR (≈ $240). Firebase Hosting is free (Spark/Blaze free tier).

## Real-launch checklist (out of scope for the MVP)

- Switch `EMAIL_PROVIDER=resend` + `SMS_PROVIDER=twilio`, set
  `ENVIRONMENT=production` (disables the dev-mailbox + `/api/v1/dev/*`).
- Rotate all secrets; lock the Maps server key to a Cloud NAT static egress IP.
- Add observability (OpenTelemetry / Cloud Trace) — not yet wired in
  `backend/app/src/app/__init__.py`.
