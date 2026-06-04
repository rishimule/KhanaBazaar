<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# `infra/` — GCP infrastructure-as-code

Khana Bazaar deploys to **Google Cloud Platform** — Cloud Run + Cloud SQL + Memorystore in `asia-south1` (Mumbai). The full target architecture, cost model, and deploy runbook live in [`docs/gcp_deployment.md`](../docs/gcp_deployment.md).

## Status

**Nothing is committed here yet.** No Terraform, no Cloud Run service manifests, no Dockerfiles. This directory is the home for that IaC once it lands; until then `docs/gcp_deployment.md` is the implementation spec.

## Planned layout

Per `docs/gcp_deployment.md` §5, deployment artifacts will live as:

```
backend/app/Dockerfile          # FastAPI image (uvicorn entrypoint); worker + beat reuse it
frontend/Dockerfile             # next build → next start (output: "standalone")
deploy/gcp/
  cloudrun-api.yaml             # Cloud Run service manifest (api)
  cloudrun-worker.yaml          # Cloud Run service manifest (worker)
  cloudrun-beat.yaml            # Cloud Run service manifest (beat)
  cloudrun-web.yaml             # Cloud Run service manifest (web)
  cloudrun-meili.yaml           # Cloud Run service manifest (meilisearch, GCS Fuse mount)
infra/                          # Terraform (Cloud SQL, Memorystore, Artifact Registry,
                                #   Secret Manager, VPC, Workload Identity Federation)
```

## First-deploy reindex (Meilisearch)

After the stack is provisioned, populate the search indexes from a one-shot Cloud Run job or `gcloud run jobs execute`:

```bash
uv run python -m app.search.reindex --all
```

Then smoke-test (Meili is internal-ingress; hit it from within the VPC / a sibling Cloud Run service):

```bash
curl -s 'https://khanabazaar-meili-<hash>-el.a.run.app/health'
# → {"status":"available"}

curl -s 'https://khanabazaar-api-<hash>-el.a.run.app/api/v1/search/suggest?q=milk'
# → {"query_id":"...","terms":[...],"products":[...],"stores":[...]}
```

See [`docs/gcp_deployment.md`](../docs/gcp_deployment.md) for the full provisioning steps, IAM wiring, and disaster recovery.
