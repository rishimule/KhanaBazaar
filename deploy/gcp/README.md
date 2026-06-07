# KhanaBazaar MVP — GCP deploy runbook

Project `khanabazaar-mvp`, region `asia-south1`. Spec:
`docs/superpowers/specs/2026-06-05-gcp-mvp-deploy-design.md`. Plan:
`docs/superpowers/plans/2026-06-05-gcp-mvp-deploy.md`.

Architecture: Cloud Run `web` + `api` (always-warm, min=1) → Cloud SQL Postgres;
Celery `worker` + Redis + Meilisearch + cloud-sql-proxy on one `e2-small` VM;
Cloud Run reaches the VM's internal IP via Direct VPC egress. Email/SMS are
captured in the dev-mailbox (`/dev-emails`, `/dev-sms`) — no real provider.

> **MVP security note:** the deployed app runs with `ENVIRONMENT=development` so
> the dev-mailbox works (it's the only OTP delivery path without Resend/Twilio).
> The `/api/v1/dev/*` endpoints are HTTP-Basic gated (`DEV_INBOX_USER` /
> `DEV_INBOX_PASSWORD`). Anyone with those creds can read login OTPs. This is a
> demo posture, not a real launch. Redis is bound to the VM internal IP only and
> requires a password; Meili requires its master key.

## First-time bootstrap (run once, in order)

```bash
export PROJECT_ID=khanabazaar-mvp REGION=asia-south1 ZONE=asia-south1-a
export REPO_SLUG=$(gh repo view --json nameWithOwner -q .nameWithOwner)
# strong secrets:
export DB_PASSWORD=$(openssl rand -base64 30)
export JWT_SECRET=$(openssl rand -base64 48)
export OTP_PEPPER=$(openssl rand -base64 48)
export MEILI_MASTER_KEY=$(openssl rand -base64 32)
export REDIS_PASSWORD=$(openssl rand -base64 24)
export DEV_INBOX_PASSWORD=$(openssl rand -base64 24)
# reuse local values (from backend/app/.env):
export GOOGLE_MAPS_SERVER_API_KEY=... VAPID_PRIVATE_KEY=... VAPID_PUBLIC_KEY=...

bash deploy/gcp/bootstrap.sh                  # APIs, AR, VPC, SQL, secrets, WIF
# Save the printed WIF_PROVIDER=... value (needed for the GitHub secret).
# then create the VM ("VM" below), first deploy ("First deploy"), wire GitHub.
```

## VM (kb-svc)

```bash
gcloud compute disks create meili-disk --size=10GB --type=pd-balanced --zone=$ZONE
gcloud compute instances create kb-svc \
  --zone=$ZONE --machine-type=e2-small --image-family=debian-12 --image-project=debian-cloud \
  --network=kb-vpc --subnet=kb-subnet \
  --disk=name=meili-disk,device-name=meili-disk,auto-delete=no \
  --service-account=kb-runtime@$PROJECT_ID.iam.gserviceaccount.com \
  --scopes=cloud-platform \
  --metadata-from-file=startup-script=deploy/gcp/vm/startup.sh

VM_IP=$(gcloud compute instances describe kb-svc --zone=$ZONE --format='value(networkInterfaces[0].networkIP)')

# push compose + write /opt/kb/.env (compose auto-loads it for interpolation):
gcloud compute ssh kb-svc --zone=$ZONE --tunnel-through-iap --command='sudo mkdir -p /opt/kb && sudo chmod 777 /opt/kb'
gcloud compute scp deploy/gcp/vm/docker-compose.yml kb-svc:/opt/kb/docker-compose.yml --zone=$ZONE --tunnel-through-iap

# Build /opt/kb/.env from deploy/gcp/vm/.env.example with real values, e.g.:
cat <<EOF | gcloud compute ssh kb-svc --zone=$ZONE --tunnel-through-iap --command='cat > /tmp/kb.env && sudo mv /tmp/kb.env /opt/kb/.env'
API_IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/kb/api:latest
VM_INTERNAL_IP=$VM_IP
MEILI_MASTER_KEY=$MEILI_MASTER_KEY
REDIS_PASSWORD=$REDIS_PASSWORD
CLOUDSQL_INSTANCE=$PROJECT_ID:$REGION:kb-pg
DATABASE_URL=postgresql+asyncpg://kbuser:$DB_PASSWORD@cloudsql-proxy:5432/khanabazaar
REDIS_URL=redis://:$REDIS_PASSWORD@redis:6379/0
MEILI_URL=http://meilisearch:7700
JWT_SECRET=$JWT_SECRET
OTP_PEPPER=$OTP_PEPPER
ENVIRONMENT=development
EMAIL_PROVIDER=console
SMS_PROVIDER=console
VAPID_PRIVATE_KEY=$VAPID_PRIVATE_KEY
VAPID_PUBLIC_KEY=$VAPID_PUBLIC_KEY
VAPID_SUBJECT=mailto:sarvakadev@gmail.com
EOF

# bring up redis + meili + proxy (worker fails until the api image exists — that's fine):
gcloud compute ssh kb-svc --zone=$ZONE --tunnel-through-iap --command='cd /opt/kb && sudo docker compose up -d'

# rewrite redis-url / meili-url secrets to the real VM internal IP (redis-url carries the password):
printf 'redis://:%s@%s:6379/0' "$REDIS_PASSWORD" "$VM_IP" | gcloud secrets versions add redis-url --data-file=-
printf 'http://%s:7700' "$VM_IP" | gcloud secrets versions add meili-url --data-file=-
```

## First deploy (creates the Cloud Run resources the workflow later only updates)

Two-pass because Next bakes the api URL at build time. See plan Task 19 for the
full commands. Summary:

1. Build + push `kb/api:latest`; create + run the `kb-migrate` job (migrate + seed + reindex).
2. `gcloud run deploy khanabazaar-api` (min=1, Direct VPC egress, `--set-secrets`, `ENVIRONMENT=development`). Capture `API_URL`.
3. Build `kb/web:latest` with `--build-arg INTERNAL_API_URL=$API_URL`; `gcloud run deploy khanabazaar-web` (min=1, runtime `INTERNAL_API_URL=$API_URL`). Capture `WEB_URL`.
4. `gcloud run services update khanabazaar-api --update-env-vars=FRONTEND_ORIGIN=$WEB_URL`.
5. Bring the worker up on the VM (`docker compose up -d worker`).
6. Add `WEB_URL/*` to the Google Maps browser-key HTTP-referrer allow-list (console).
7. Smoke (also proves Cloud Run → VM reachability over Direct VPC egress):
   - `curl $API_URL/health` → `{"status":"ok"}`
   - `curl "$API_URL/api/v1/search/suggest?q=milk"` → products/terms (**exercises Meilisearch** on the VM)
   - `curl -X POST $API_URL/api/v1/auth/otp/request -H 'content-type: application/json' -d '{"email":"customer@khanabazaar.dev"}'` → 200 (**exercises Redis** on the VM; OTP then readable at `$WEB_URL/dev-emails`)
   - `curl -u devuser:$DEV_INBOX_PASSWORD $API_URL/api/v1/dev/emails?limit=1` → JSON (dev-mailbox + Basic auth)
   - If the search/OTP calls hang or 5xx, Cloud Run can't reach the VM — recheck the `kb-allow-internal` firewall and that the api revision attached `kb-subnet` via Direct VPC egress.

## Wire GitHub (repo variables + secrets)

```bash
gh variable set GCP_PROJECT_ID --body "khanabazaar-mvp"
gh variable set GCP_REGION --body "asia-south1"
gh variable set GCP_ZONE --body "asia-south1-a"
gh variable set INTERNAL_API_URL --body "$API_URL"
gh secret set GCP_WIF_PROVIDER --body "<WIF_PROVIDER printed by bootstrap.sh>"
gh secret set NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY --body "<browser key>"
gh secret set NEXT_PUBLIC_VAPID_PUBLIC_KEY --body "<vapid public>"
```

## Redeploy

Merge to `main` → `.github/workflows/deploy.yml` runs automatically (build api+web,
migrate-seed job, deploy api/web, restart worker on the VM).

## Deploy hardening

- The deploy workflow uses `concurrency: { group: deploy-main, cancel-in-progress: false }`,
  so back-to-back merges queue instead of racing on Cloud Run updates (which otherwise
  hit `ABORTED: Conflict`).
- Artifact Registry has a cleanup policy (`deploy/gcp/ar-cleanup-policy.json`): keep the
  10 newest versions of each image, delete versions older than 30 days. AR evaluates it
  asynchronously (~daily); Cloud Run pins running images by digest so a pruned tag never
  breaks the live revision. Re-apply with:
  ```bash
  gcloud artifacts repositories set-cleanup-policies kb --location=asia-south1 \
    --project=khanabazaar-mvp --policy=deploy/gcp/ar-cleanup-policy.json
  ```

## Rollback

```bash
gcloud run services update-traffic khanabazaar-api --region=$REGION --to-revisions=PREV=100
```

## Budget alert (alert-only, $250)

```bash
# NOTE: this billing account's currency is INR — --budget-amount currency must
# match (USD is rejected with INVALID_ARGUMENT). 20000 INR ≈ $240.
# Enable the API first: gcloud services enable billingbudgets.googleapis.com
BILLING=01C02F-FB1938-E2F6B2
gcloud billing budgets create --billing-account=$BILLING \
  --display-name="kb-mvp-budget" --budget-amount=20000INR \
  --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0
```

## Custom domain — khanabazaar.rishimule.dev (Firebase Hosting)

The web service is also served at `https://khanabazaar.rishimule.dev` via Firebase
Hosting (free) rewriting to the `khanabazaar-web` Cloud Run service. Config:
`firebase.json` + `.firebaserc` at repo root. Spec/plan:
`docs/superpowers/specs/2026-06-06-custom-domain-firebase-hosting-design.md`.

- Firebase is enabled on the same `khanabazaar-mvp` GCP project (added via the
  Firebase console — the CLI `projects:addfirebase` 403s on a missing
  `cloud-platform` OAuth scope).
- DNS at name.com: a single **CNAME** `khanabazaar` → `khanabazaar-mvp.web.app`.
  Apex/`www` (the GitHub-Pages portfolio, `185.199.108–111.153`) are untouched.
- Managed TLS cert auto-provisions after the CNAME verifies (took ~20 min here).
- `FRONTEND_ORIGIN` on `khanabazaar-api` includes `https://khanabazaar.rishimule.dev`;
  the Maps browser key allows `https://khanabazaar.rishimule.dev/*` as a referrer.
- Both the `*.run.app` URL and the custom domain serve the same Cloud Run service.

Redeploy hosting (only needed if `firebase.json` changes — the rewrite tracks the
live Cloud Run service automatically):
```bash
firebase deploy --only hosting --project khanabazaar-mvp
```
Re-check domain/cert status: Firebase Console → Hosting → domain row (`Connected`).

## Teardown

```bash
gcloud run services delete khanabazaar-api khanabazaar-web --region=$REGION
gcloud run jobs delete kb-migrate --region=$REGION
gcloud compute instances delete kb-svc --zone=$ZONE
gcloud sql instances delete kb-pg
# custom domain: remove in Firebase console + delete the CNAME at name.com
```
