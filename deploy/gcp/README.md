# Khana Bazaar — GCP first-deploy runbook (credit-funded, release branch)

Spec: `docs/superpowers/specs/2026-06-04-gcp-credit-deploy-release-branch-design.md`.
All commands run from the repo root unless noted. Region `asia-south1`.

## 0. Project + billing
```bash
gcloud auth login
# Project IDs are GLOBALLY UNIQUE — pick one that's free (e.g. khanabazaar-app).
export PROJECT_ID=khanabazaar-app
gcloud projects create "$PROJECT_ID" --name="Khana Bazaar"
gcloud beta billing projects link "$PROJECT_ID" --billing-account=XXXX-XXXX-XXXX
```
**Set the budget alert now, before provisioning** (don't wait until the end):
Billing → Budgets & alerts → create a $250 budget with alerts at 50/90/100%.
The trial pauses at $300 / 90 days on its own, but the alert is your early warning.

## 1. Provision
```bash
export PROJECT_ID REGION=asia-south1 GH_REPO=rishimule/KhanaBazaar
export DB_PASSWORD="$(openssl rand -hex 16)"
bash deploy/gcp/bootstrap.sh
# PostGIS: NO manual step needed. The kb-migrate job (step 4) runs migration
# 8bd3769f0789_enable_postgis (CREATE EXTENSION postgis) + pg_trgm as kb_app,
# which holds cloudsqlsuperuser. (`gcloud sql connect` can't reach the private-
# IP instance anyway.)
# Replace the Maps key placeholders with real values:
echo -n "REAL_SERVER_KEY"  | gcloud secrets versions add gmaps-server-key  --data-file=-
echo -n "REAL_BROWSER_KEY" | gcloud secrets versions add gmaps-browser-key --data-file=-
# The BROWSER key is HTTP-referrer-restricted: add the prod web origin or the
# map fails with RefererNotAllowedMapError. Allow both *.run.app URL forms and
# target the Maps JS + Places APIs:
#   gcloud services api-keys update <BROWSER_KEY_UID> \
#     --allowed-referrers="https://khanabazaar-web-<PROJECT_NUMBER>.<REGION>.run.app/*,https://<other-runapp-form>/*" \
#     --api-target=service=maps-backend.googleapis.com \
#     --api-target=service=places-backend.googleapis.com
```

## 2. Bootstrap images
```bash
export AR_HOST=asia-south1-docker.pkg.dev
gcloud auth configure-docker $AR_HOST --quiet
docker build -t $AR_HOST/$PROJECT_ID/kb/api:bootstrap -f backend/app/Dockerfile backend/app
docker push   $AR_HOST/$PROJECT_ID/kb/api:bootstrap
# INTERNAL_API_URL MUST be a build-arg: Next.js resolves rewrites() at build
# time into the route manifest, so the /api/v1/* -> api proxy destination is
# frozen at build (a runtime env var only affects RSC fetches, not the proxy).
# The api URL is predictable before deploy: https://khanabazaar-api-<PROJECT_NUMBER>.<REGION>.run.app
export API_URL="https://khanabazaar-api-$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)').$REGION.run.app"
docker build -t $AR_HOST/$PROJECT_ID/kb/web:bootstrap \
  --build-arg NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY="REAL_BROWSER_KEY" \
  --build-arg INTERNAL_API_URL="$API_URL" \
  -f frontend/Dockerfile frontend
docker push   $AR_HOST/$PROJECT_ID/kb/web:bootstrap

# If you build with Cloud Build instead (no local Docker):
#   gcloud builds submit frontend --config=deploy/gcp/cloudbuild-web.yaml \
#     --substitutions=_IMAGE=$AR_HOST/$PROJECT_ID/kb/web:bootstrap,_BROWSER_KEY=REAL_BROWSER_KEY,_INTERNAL_API_URL=$API_URL
export SA=kb-runtime@$PROJECT_ID.iam.gserviceaccount.com
```

## 3. Meilisearch (public ingress, key-gated)
```bash
gcloud run deploy khanabazaar-meili --region=$REGION \
  --image=getmeili/meilisearch:v1.11 --service-account=$SA \
  --cpu=1 --memory=2Gi --no-cpu-throttling \
  --min-instances=1 --max-instances=1 --concurrency=80 --port=7700 \
  --allow-unauthenticated \
  --add-volume=name=meili-data,type=cloud-storage,bucket=${PROJECT_ID}-meili-data \
  --add-volume-mount=volume=meili-data,mount-path=/meili_data \
  --set-env-vars=MEILI_ENV=production,MEILI_NO_ANALYTICS=true \
  --set-secrets=MEILI_MASTER_KEY=meili-master-key:latest
export MEILI_URL=$(gcloud run services describe khanabazaar-meili --region=$REGION --format='value(status.url)')
curl -H "Authorization: Bearer $(gcloud secrets versions access latest --secret=meili-master-key)" "$MEILI_URL/health"
```

## 4. Migrate + seed (Cloud Run Jobs)
```bash
COMMON_VPC="--network=kb-vpc --subnet=kb-subnet --vpc-egress=private-ranges-only"
gcloud run jobs create kb-migrate --region=$REGION \
  --image=$AR_HOST/$PROJECT_ID/kb/api:bootstrap --service-account=$SA $COMMON_VPC \
  --set-secrets=DATABASE_URL=database-url:latest \
  --command=alembic --args=upgrade,head
gcloud run jobs execute kb-migrate --region=$REGION --wait

# Seed (full dev seed -> catalog + demo stores + admin@khanabazaar.dev). One-time.
# Runs scripts/seed_database.py, which seeds demo data AND reindexes Meili.
# (NOTE: `python -m app.db.dev_seed` is NOT a runnable entrypoint — dev_seed.py
#  has no __main__; the runnable seeder is scripts/seed_database.py.)
# Because this reindexes, the separate kb-reindex job in step 6 is optional.
gcloud run jobs create kb-seed --region=$REGION \
  --image=$AR_HOST/$PROJECT_ID/kb/api:bootstrap --service-account=$SA $COMMON_VPC \
  --set-env-vars=ENVIRONMENT=production,MEILI_URL=$MEILI_URL \
  --set-secrets=DATABASE_URL=database-url:latest,REDIS_URL=redis-url:latest,JWT_SECRET=jwt-secret:latest,OTP_PEPPER=otp-pepper:latest,MEILI_MASTER_KEY=meili-master-key:latest \
  --command=python --args=scripts/seed_database.py
gcloud run jobs execute kb-seed --region=$REGION --wait
```

## 5. Deploy api -> worker -> web
```bash
RUNTIME_SECRETS="JWT_SECRET=jwt-secret:latest,OTP_PEPPER=otp-pepper:latest,DATABASE_URL=database-url:latest,REDIS_URL=redis-url:latest,MEILI_MASTER_KEY=meili-master-key:latest,GOOGLE_MAPS_SERVER_API_KEY=gmaps-server-key:latest,DEV_LOGS_USERNAME=dev-logs-username:latest,DEV_LOGS_PASSWORD=dev-logs-password:latest"

# api
# max-instances=3 caps DB usage at 3 × (pool_size 2 + max_overflow 3) = 15
# connections, leaving headroom under db-f1-micro's ~22 usable (worker ~2 +
# deploy jobs). Raise only alongside a larger Cloud SQL tier. (web below stays
# at 5 — it proxies to the api and never connects to Postgres.)
gcloud run deploy khanabazaar-api --region=$REGION \
  --image=$AR_HOST/$PROJECT_ID/kb/api:bootstrap --service-account=$SA $COMMON_VPC \
  --cpu=1 --memory=512Mi --min-instances=1 --max-instances=3 --concurrency=40 --port=8080 \
  --allow-unauthenticated \
  --set-env-vars=ENVIRONMENT=production,API_V1_STR=/api/v1,EMAIL_PROVIDER=console,SMS_PROVIDER=console,EXPOSE_DEV_OTPS=true,MEILI_URL=$MEILI_URL \
  --set-secrets=$RUNTIME_SECRETS
export API_URL=$(gcloud run services describe khanabazaar-api --region=$REGION --format='value(status.url)')

# worker (Celery + embedded beat; internal ingress; CPU always allocated)
gcloud run deploy khanabazaar-worker --region=$REGION \
  --image=$AR_HOST/$PROJECT_ID/kb/api:bootstrap --service-account=$SA $COMMON_VPC \
  --cpu=1 --memory=512Mi --no-cpu-throttling --min-instances=1 --max-instances=1 \
  --no-allow-unauthenticated --ingress=internal \
  --command=sh \
  --args='^@^-c@celery -A app.core.celery_app worker -B --loglevel=info --concurrency=2 & exec python -m http.server "$PORT"' \
  --set-env-vars=ENVIRONMENT=production,EMAIL_PROVIDER=console,SMS_PROVIDER=console,MEILI_URL=$MEILI_URL \
  --set-secrets=JWT_SECRET=jwt-secret:latest,OTP_PEPPER=otp-pepper:latest,DATABASE_URL=database-url:latest,REDIS_URL=redis-url:latest,MEILI_MASTER_KEY=meili-master-key:latest,GOOGLE_MAPS_SERVER_API_KEY=gmaps-server-key:latest

# web (INTERNAL_API_URL at runtime — drives both the next.config rewrite and
# server-side RSC fetches in lib/api.ts)
gcloud run deploy khanabazaar-web --region=$REGION \
  --image=$AR_HOST/$PROJECT_ID/kb/web:bootstrap --service-account=$SA \
  --cpu=1 --memory=512Mi --min-instances=1 --max-instances=5 --concurrency=80 --port=8080 \
  --allow-unauthenticated \
  --set-env-vars=INTERNAL_API_URL=$API_URL
export WEB_URL=$(gcloud run services describe khanabazaar-web --region=$REGION --format='value(status.url)')

# second pass: tell api its CORS origin
gcloud run services update khanabazaar-api --region=$REGION \
  --update-env-vars=FRONTEND_ORIGIN=$WEB_URL
```

## 6. Reindex search + smoke test
```bash
gcloud run jobs create kb-reindex --region=$REGION \
  --image=$AR_HOST/$PROJECT_ID/kb/api:bootstrap --service-account=$SA $COMMON_VPC \
  --set-env-vars=ENVIRONMENT=production,MEILI_URL=$MEILI_URL \
  --set-secrets=DATABASE_URL=database-url:latest,REDIS_URL=redis-url:latest,MEILI_MASTER_KEY=meili-master-key:latest \
  --command=python --args=-m,app.search.reindex,--all
gcloud run jobs execute kb-reindex --region=$REGION --wait

curl "$WEB_URL/"
curl "$WEB_URL/api/v1/meta/health"
curl "$WEB_URL/api/v1/search/suggest?q=milk"
```

## 7. Log in as admin
1. `POST $WEB_URL/api/v1/auth/otp/request` with `{"email":"admin@khanabazaar.dev"}`.
2. Open `$WEB_URL/dev-logs`, sign in with `dev-logs-username` / `dev-logs-password`
   (`gcloud secrets versions access latest --secret=dev-logs-password`), read the code.
3. `POST .../auth/otp/verify` to get the JWT. Confirm the worker logged the email task in Cloud Logging.

## 8. Budget alert + CI
- Billing -> Budgets & alerts -> create a budget at ~$250 (alert at 50/90/100%).
- Set GitHub repo secrets: `GCP_PROJECT_ID`, `GCP_PROJECT_NUMBER`, `GCP_REGION`,
  `GCP_WIF_PROVIDER` (`projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/gh-pool/providers/gh-provider`),
  `GCP_DEPLOYER_SA` (`kb-deployer@$PROJECT_ID.iam.gserviceaccount.com`),
  `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY`,
  `INTERNAL_API_URL` (`https://khanabazaar-api-$PROJECT_NUMBER.$REGION.run.app` — baked into the web build),
  `NEXT_PUBLIC_VAPID_PUBLIC_KEY` (Web Push browser key — baked into the web build).

**Web Push (VAPID):** generate a raw-base64url EC P-256 keypair (NOT a PKCS8 PEM
— `pywebpush` rejects PEM). Store the 43-char private key in secret
`vapid-private-key`; set `VAPID_PUBLIC_KEY` (87-char) + `VAPID_SUBJECT`
(real deliverable `mailto:` / `https:` — Apple rejects `.example`) as env on the
**api and worker**, mount `VAPID_PRIVATE_KEY=vapid-private-key:latest`, and pass
the public key as the `NEXT_PUBLIC_VAPID_PUBLIC_KEY` web build-arg. Push no-ops
if any are unset.
- Push to `release` -> CI builds, migrates, and updates the services.

## Teardown
`gcloud projects delete $PROJECT_ID` removes everything (stops all billing).
