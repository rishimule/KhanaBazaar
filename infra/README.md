<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# `infra/` — Bicep modules

Per-service Bicep templates wired together by `azd` (`azure.yaml` not yet committed). Tracked in `docs/azure_deployment.md`.

## Current modules

| File | What |
|---|---|
| `modules/meilisearch.bicep` | Meilisearch v1.11 Container App + Azure Files persistent share for `/meili_data`. Internal-only ingress, single replica. |

## Wiring `meilisearch.bicep` into `main.bicep`

Once a top-level `main.bicep` is committed, wire it like:

```bicep
module meilisearch './modules/meilisearch.bicep' = {
  name: 'meilisearch'
  params: {
    location: location
    environmentId: env.id
    environmentName: env.name
    logAnalyticsWorkspaceId: logAnalytics.id
    meiliMasterKey: keyVault.getSecret('meili-master-key')
  }
}

// Pass to the api + worker apps as MEILI_URL / MEILI_MASTER_KEY env vars.
output meiliUrl string = meilisearch.outputs.meiliInternalUrl
```

## First-deploy runbook (Meilisearch)

After `azd up` provisions everything:

```bash
# from a one-shot Container App job, or `az containerapp exec` into the api app
uv run python -m app.search.reindex --all
```

Then smoke:

```bash
curl -s 'http://kb-prod-meili-cin:7700/health'
# → {"status":"available"}

curl -s 'https://kb-prod-api-cin/api/v1/search/suggest?q=milk'
# → {"query_id":"...","terms":[...],"products":[...],"stores":[...]}
```

See `docs/azure_deployment.md` §7.5b for the full runbook + disaster recovery.
