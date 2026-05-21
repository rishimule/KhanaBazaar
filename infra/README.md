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
    // Bicep reads the value at deploy time via keyVault.getSecret(...).
    // The module then re-stores it as a Container App secret and exposes
    // it to the meili container via secretRef — the proper Container Apps
    // pattern. NEVER use the App Service @Microsoft.KeyVault(...) syntax;
    // Container Apps does not support it.
    meiliMasterKey: keyVault.getSecret('meili-master-key')
  }
}

// Downstream api / worker / beat apps reference the master key the same
// way: declare a Container App secret of name `meili-master-key` with
// `keyVaultUrl` + `identity`, then bind via `env: [{ name: 'MEILI_MASTER_KEY',
// secretRef: 'meili-master-key' }]`.
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
