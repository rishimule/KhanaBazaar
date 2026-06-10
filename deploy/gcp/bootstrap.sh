#!/usr/bin/env bash
# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# One-time GCP provisioning for the KhanaBazaar MVP. Re-runnable.
set -euo pipefail

PROJECT_ID=${PROJECT_ID:-khanabazaar-mvp}
REGION=${REGION:-asia-south1}
ZONE=${ZONE:-asia-south1-a}
REPO_SLUG=${REPO_SLUG:?set REPO_SLUG=owner/repo}
PROJECT_NUM=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
gcloud config set project "$PROJECT_ID"

echo "==> 1. Enable APIs"
gcloud services enable run.googleapis.com sqladmin.googleapis.com compute.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com \
  iamcredentials.googleapis.com vpcaccess.googleapis.com

echo "==> 2. Artifact Registry"
gcloud artifacts repositories describe kb --location="$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create kb --repository-format=docker --location="$REGION"
# Cap image storage: keep the 10 newest versions of each image, delete >30d.
# Cleanup policies are evaluated asynchronously by Artifact Registry (~daily).
gcloud artifacts repositories set-cleanup-policies kb --location="$REGION" \
  --policy="$(dirname "$0")/ar-cleanup-policy.json"

echo "==> 3. VPC + subnet + firewall"
gcloud compute networks describe kb-vpc >/dev/null 2>&1 || \
  gcloud compute networks create kb-vpc --subnet-mode=custom
gcloud compute networks subnets describe kb-subnet --region="$REGION" >/dev/null 2>&1 || \
  gcloud compute networks subnets create kb-subnet --network=kb-vpc \
    --region="$REGION" --range=10.10.0.0/24
# Cloud Run Direct VPC egress range -> VM Redis/Meili
gcloud compute firewall-rules describe kb-allow-internal >/dev/null 2>&1 || \
  gcloud compute firewall-rules create kb-allow-internal --network=kb-vpc \
    --allow=tcp:6379,tcp:7700 --source-ranges=10.10.0.0/24
# IAP SSH (for CI compute ssh + admin)
gcloud compute firewall-rules describe kb-allow-iap-ssh >/dev/null 2>&1 || \
  gcloud compute firewall-rules create kb-allow-iap-ssh --network=kb-vpc \
    --allow=tcp:22 --source-ranges=35.235.240.0/20

echo "==> 4. Cloud SQL (Postgres 15 + PostGIS)"
gcloud sql instances describe kb-pg >/dev/null 2>&1 || \
  gcloud sql instances create kb-pg --database-version=POSTGRES_15 \
    --tier=db-f1-micro --region="$REGION" --storage-size=10 --storage-type=SSD \
    --no-backup
gcloud sql databases describe khanabazaar --instance=kb-pg >/dev/null 2>&1 || \
  gcloud sql databases create khanabazaar --instance=kb-pg
# DB user (password from env DB_PASSWORD)
gcloud sql users list --instance=kb-pg --format='value(name)' | grep -qx kbuser || \
  gcloud sql users create kbuser --instance=kb-pg --password="${DB_PASSWORD:?set DB_PASSWORD}"
# NOTE: PostGIS extension is created by the kb-migrate job (deploy_release.sh),
# which runs in-VPC via the Cloud SQL connector — reliable and loud on failure,
# unlike a laptop-side `gcloud sql connect` IP-whitelist dance.
# The instance is left with NO authorized networks: its public IP rejects all
# direct connections; only the authenticated connector/proxy path works.

echo "==> 5. Secret Manager"
create_secret () {  # name value
  gcloud secrets describe "$1" >/dev/null 2>&1 || gcloud secrets create "$1" --replication-policy=automatic
  printf '%s' "$2" | gcloud secrets versions add "$1" --data-file=-
}
INSTANCE_CONN="$PROJECT_ID:$REGION:kb-pg"
create_secret database-url "postgresql+asyncpg://kbuser:${DB_PASSWORD}@/khanabazaar?host=/cloudsql/${INSTANCE_CONN}"
create_secret jwt-secret    "${JWT_SECRET:?}"
create_secret otp-pepper    "${OTP_PEPPER:?}"
create_secret meili-master-key "${MEILI_MASTER_KEY:?}"
create_secret dev-inbox-password "${DEV_INBOX_PASSWORD:?}"
create_secret redis-password "${REDIS_PASSWORD:?}"
# redis-url/meili-url are placeholders; rewritten with the real VM internal IP
# after the VM exists (Task 11). redis-url carries the requirepass password.
create_secret redis-url     "redis://:${REDIS_PASSWORD}@10.10.0.0:6379/0"
create_secret meili-url     "http://10.10.0.0:7700"
create_secret google-maps-server-key "${GOOGLE_MAPS_SERVER_API_KEY:?}"
create_secret vapid-private-key "${VAPID_PRIVATE_KEY:?}"
create_secret vapid-public-key  "${VAPID_PUBLIC_KEY:?}"

echo "==> 6. Runtime service account for Cloud Run + jobs"
gcloud iam service-accounts describe kb-runtime@$PROJECT_ID.iam.gserviceaccount.com >/dev/null 2>&1 || \
  gcloud iam service-accounts create kb-runtime --display-name="KB Cloud Run runtime"
# artifactregistry.reader: the VM worker pulls the api image via kb-runtime ADC.
# (Cloud Run services pull via the Run service agent and don't need this, but the VM does.)
for ROLE in roles/cloudsql.client roles/secretmanager.secretAccessor roles/artifactregistry.reader; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:kb-runtime@$PROJECT_ID.iam.gserviceaccount.com" --role="$ROLE" --condition=None
done

echo "==> 6b. Product images bucket (public-read, CDN-cacheable)"
# Product photos are non-sensitive; public-read + immutable content-hash object
# keys make them cacheable forever, so a CDN can front the bucket later with no
# code change (set GCS_PUBLIC_BASE_URL). Signed reads were rejected — they expire
# and defeat caching. If org policy forbids --no-public-access-prevention, keep
# the bucket private and front it with Cloud CDN instead of reverting to signed
# reads, then point GCS_PUBLIC_BASE_URL at the CDN domain.
IMAGES_BUCKET="kb-product-images-${PROJECT_ID}"
gcloud storage buckets describe "gs://${IMAGES_BUCKET}" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${IMAGES_BUCKET}" \
    --location="$REGION" --uniform-bucket-level-access --no-public-access-prevention
gcloud storage buckets add-iam-policy-binding "gs://${IMAGES_BUCKET}" \
  --member="allUsers" --role="roles/storage.objectViewer" --condition=None
# CORS so an admin can re-fetch a hosted image into a canvas to re-edit it.
# Tighten "origin" to the real web origin(s) before launch.
cat > /tmp/kb-images-cors.json <<'JSON'
[{"origin":["*"],"method":["GET"],"responseHeader":["Content-Type"],"maxAgeSeconds":3600}]
JSON
gcloud storage buckets update "gs://${IMAGES_BUCKET}" --cors-file=/tmp/kb-images-cors.json
# Runtime SA (Cloud Run api) needs write/delete on the bucket.
gcloud storage buckets add-iam-policy-binding "gs://${IMAGES_BUCKET}" \
  --member="serviceAccount:kb-runtime@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin" --condition=None

echo "==> 7. WIF pool + provider + deployer SA"
gcloud iam workload-identity-pools describe gh-pool --location=global >/dev/null 2>&1 || \
  gcloud iam workload-identity-pools create gh-pool --location=global --display-name="GitHub"
gcloud iam workload-identity-pools providers describe gh-provider \
  --location=global --workload-identity-pool=gh-pool >/dev/null 2>&1 || \
  gcloud iam workload-identity-pools providers create-oidc gh-provider \
    --location=global --workload-identity-pool=gh-pool \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository=='${REPO_SLUG}'"
gcloud iam service-accounts describe gh-deployer@$PROJECT_ID.iam.gserviceaccount.com >/dev/null 2>&1 || \
  gcloud iam service-accounts create gh-deployer --display-name="GitHub Actions deployer"
for ROLE in roles/run.admin roles/iam.serviceAccountUser roles/artifactregistry.writer \
            roles/cloudsql.client roles/secretmanager.secretAccessor \
            roles/compute.instanceAdmin.v1 roles/iap.tunnelResourceAccessor; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:gh-deployer@$PROJECT_ID.iam.gserviceaccount.com" --role="$ROLE" --condition=None
done
# Let GitHub repo impersonate the deployer SA
gcloud iam service-accounts add-iam-policy-binding \
  gh-deployer@$PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUM}/locations/global/workloadIdentityPools/gh-pool/attribute.repository/${REPO_SLUG}"

echo "==> bootstrap core complete. Next: create the VM (Task 11) and first deploy (Task 19)."
echo "WIF_PROVIDER=projects/${PROJECT_NUM}/locations/global/workloadIdentityPools/gh-pool/providers/gh-provider"
