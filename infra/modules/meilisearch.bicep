// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or
// distributed without explicit permission from the author.
//
// Meilisearch Container App + Azure Files share for persistent index data.
// Internal-only ingress — reached over the managed environment's private
// network by `kb-prod-api-cin` and `kb-prod-worker-cin`.

@description('Azure region (e.g. centralindia).')
param location string

@description('Resource ID of the existing Container Apps Managed Environment.')
param environmentId string

@description('Resource ID of the existing Log Analytics workspace used by the environment.')
param logAnalyticsWorkspaceId string

@description('Container Apps environment name (extracted for storage definition).')
param environmentName string

@description('Meilisearch master key. Pass from Key Vault via @Microsoft.KeyVault(...).')
@secure()
param meiliMasterKey string

@description('Container image tag for getmeili/meilisearch.')
param image string = 'getmeili/meilisearch:v1.11'

@description('Storage account name for the Azure Files share. Globally unique.')
param storageAccountName string = 'meili${uniqueString(resourceGroup().id)}'

// ── Azure Files: persistent storage for /meili_data ──────────────────────

resource storageAccount 'Microsoft.Storage/storageAccounts@2024-01-01' = {
  name: storageAccountName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2024-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource share 'Microsoft.Storage/storageAccounts/fileServices/shares@2024-01-01' = {
  parent: fileService
  name: 'meili-data'
  properties: {
    shareQuota: 50  // GB; bump as catalog grows
    enabledProtocols: 'SMB'
  }
}

// ── Container Apps Environment storage definition ────────────────────────

resource env 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: environmentName
}

resource meiliStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: env
  name: 'meili-data'
  properties: {
    azureFile: {
      accountName: storageAccount.name
      accountKey: storageAccount.listKeys().keys[0].value
      shareName: share.name
      accessMode: 'ReadWrite'
    }
  }
}

// ── Meilisearch Container App ────────────────────────────────────────────

resource meili 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'kb-prod-meili-cin'
  location: location
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      ingress: {
        external: false
        targetPort: 7700
        transport: 'tcp'
        allowInsecure: true   // internal-only; TLS is environment-mediated
      }
      secrets: [
        { name: 'meili-master-key', value: meiliMasterKey }
      ]
    }
    template: {
      containers: [
        {
          name: 'meilisearch'
          image: image
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: [
            { name: 'MEILI_MASTER_KEY', secretRef: 'meili-master-key' }
            { name: 'MEILI_ENV', value: 'production' }
            { name: 'MEILI_NO_ANALYTICS', value: 'true' }
          ]
          volumeMounts: [
            { volumeName: 'meili-data', mountPath: '/meili_data' }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 7700 }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 7700 }
              initialDelaySeconds: 5
              periodSeconds: 10
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'meili-data'
          storageType: 'AzureFile'
          storageName: meiliStorage.name
        }
      ]
      scale: {
        // Meilisearch is single-writer / single-reader — never scale out.
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

// ── Outputs ──────────────────────────────────────────────────────────────

@description('Internal in-environment URL. Wire into the api/worker container as MEILI_URL.')
output meiliInternalUrl string = 'http://${meili.name}:7700'

@description('Container App name for downstream references.')
output meiliAppName string = meili.name
