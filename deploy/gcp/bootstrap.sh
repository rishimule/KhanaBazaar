#!/usr/bin/env bash
# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# Provisions the cheapest-viable Khana Bazaar GCP stack (VM Redis, public-but-
# key-gated Meili, embedded-beat worker). Run after `gcloud auth login` and
# after creating + billing-linking the project. Edit the vars below first.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID (globally unique)}"
REGION="${REGION:-asia-south1}"
ZONE="${ZONE:-asia-south1-a}"
GH_REPO="${GH_REPO:-rishimule/KhanaBazaar}"
DB_PASSWORD="${DB_PASSWORD:?set DB_PASSWORD}"

gcloud config set project "$PROJECT_ID"

echo "== Enable APIs =="
gcloud services enable \
  run.googleapis.com sqladmin.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com storage.googleapis.com servicenetworking.googleapis.com \
  compute.googleapis.com cloudresourcemanager.googleapis.com iam.googleapis.com \
  iamcredentials.googleapis.com logging.googleapis.com monitoring.googleapis.com

echo "== VPC + subnet + private service access =="
gcloud compute networks create kb-vpc --subnet-mode=custom
gcloud compute networks subnets create kb-subnet \
  --network=kb-vpc --region="$REGION" --range=10.10.0.0/20
gcloud compute addresses create google-managed-services-kb-vpc \
  --global --purpose=VPC_PEERING --prefix-length=24 --network=kb-vpc
gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges=google-managed-services-kb-vpc --network=kb-vpc

echo "== Cloud SQL (Postgres 15, private IP) =="
# PITR + automated backups are intentionally OFF: this is a re-seedable test
# deployment (see spec §4.7), so WAL/backup storage would be pure credit waste.
gcloud sql instances create kb-pg \
  --database-version=POSTGRES_15 --tier=db-f1-micro --region="$REGION" \
  --storage-size=10GB --storage-type=SSD --no-storage-auto-increase \
  --network="projects/$PROJECT_ID/global/networks/kb-vpc" \
  --no-assign-ip --no-backup --availability-type=ZONAL
gcloud sql databases create khanabazaar --instance=kb-pg
gcloud sql users create kb_app --instance=kb-pg --password="$DB_PASSWORD"
echo ">> Now enable PostGIS: gcloud sql connect kb-pg --user=postgres --database=khanabazaar"
echo ">>   then run: CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS postgis_topology;"
DB_IP=$(gcloud sql instances describe kb-pg --format='value(ipAddresses[0].ipAddress)')
echo ">> Cloud SQL private IP: $DB_IP"

echo "== Redis VM (e2-micro) =="
# NOTE: e2-micro is NOT always-free in asia-south1 (free tier is us-west1/
# us-central1/us-east1 only) — it bills ~$7/mo here, as the cost model assumes.
# pd-standard boot disk is cheaper than the default balanced disk.
# The VM gets an EPHEMERAL EXTERNAL IP (no --no-address) so the startup script
# can apt-install redis-server on first boot — a private-only VM in this custom
# VPC has NO internet path (no Cloud NAT) and the install fails. Inbound is
# still fully blocked: this custom VPC has no default allow rules, and the only
# ingress rule (below) permits tcp:6379 from the subnet range to tag=redis only.
# So Redis is reachable solely from inside the VPC; the external IP is outbound-
# only in practice. (Avoids the ~$32/mo Cloud NAT gateway.)
gcloud compute instances create kb-redis-vm \
  --machine-type=e2-micro --zone="$ZONE" \
  --image-family=debian-12 --image-project=debian-cloud \
  --boot-disk-size=10GB --boot-disk-type=pd-standard \
  --network=kb-vpc --subnet=kb-subnet \
  --metadata-from-file=startup-script=deploy/gcp/redis-vm-startup.sh --tags=redis
gcloud compute firewall-rules create allow-redis-internal \
  --network=kb-vpc --direction=INGRESS --action=ALLOW \
  --rules=tcp:6379 --source-ranges=10.10.0.0/20 --target-tags=redis
REDIS_IP=$(gcloud compute instances describe kb-redis-vm --zone="$ZONE" \
  --format='value(networkInterfaces[0].networkIP)')
echo ">> Redis private IP: $REDIS_IP"

echo "== GCS bucket for Meili + Artifact Registry =="
gcloud storage buckets create "gs://${PROJECT_ID}-meili-data" \
  --location="$REGION" --uniform-bucket-level-access
gcloud artifacts repositories create kb --location="$REGION" --repository-format=docker
# Cap image storage: CI pushes 2 per-SHA images per deploy. Keep the 5 newest
# versions, delete anything older than 7 days — prevents unbounded AR growth.
gcloud artifacts repositories set-cleanup-policies kb --location="$REGION" \
  --policy=deploy/gcp/ar-cleanup-policy.json --no-dry-run

echo "== Service accounts + IAM =="
gcloud iam service-accounts create kb-runtime
gcloud iam service-accounts create kb-deployer
# Let the new SAs propagate before binding roles — add-iam-policy-binding
# otherwise intermittently fails with "Service account ... does not exist".
sleep 15
SA="kb-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
for ROLE in cloudsql.client secretmanager.secretAccessor logging.logWriter \
            monitoring.metricWriter storage.objectUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA" --role="roles/$ROLE"
done

echo "== Secrets =="
echo -n "$(openssl rand -hex 32)" | gcloud secrets create jwt-secret --data-file=-
echo -n "$(openssl rand -hex 32)" | gcloud secrets create otp-pepper --data-file=-
echo -n "$(openssl rand -hex 32)" | gcloud secrets create meili-master-key --data-file=-
echo -n "postgresql+asyncpg://kb_app:${DB_PASSWORD}@${DB_IP}:5432/khanabazaar" \
  | gcloud secrets create database-url --data-file=-
echo -n "redis://${REDIS_IP}:6379/0" | gcloud secrets create redis-url --data-file=-
echo -n "REPLACE_WITH_GMAPS_SERVER_KEY" | gcloud secrets create gmaps-server-key --data-file=-
echo -n "REPLACE_WITH_GMAPS_BROWSER_KEY" | gcloud secrets create gmaps-browser-key --data-file=-
echo -n "devuser" | gcloud secrets create dev-logs-username --data-file=-
echo -n "$(openssl rand -hex 24)" | gcloud secrets create dev-logs-password --data-file=-

echo "== Workload Identity Federation (GitHub Actions) =="
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
gcloud iam workload-identity-pools create gh-pool \
  --location=global --display-name="GitHub Actions"
gcloud iam workload-identity-pools providers create-oidc gh-provider \
  --location=global --workload-identity-pool=gh-pool --display-name="GitHub OIDC" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${GH_REPO}'" \
  --issuer-uri="https://token.actions.githubusercontent.com"
gcloud iam service-accounts add-iam-policy-binding \
  "kb-deployer@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/gh-pool/attribute.repository/${GH_REPO}"
for ROLE in run.admin artifactregistry.writer iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:kb-deployer@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/$ROLE"
done
# Let the deployer act as the runtime SA when deploying services.
gcloud iam service-accounts add-iam-policy-binding "$SA" \
  --member="serviceAccount:kb-deployer@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role=roles/iam.serviceAccountUser

echo "== Done. Next: docs in deploy/gcp/README.md (build images, migrate, seed, deploy). =="
echo "PROJECT_NUMBER=$PROJECT_NUMBER"
