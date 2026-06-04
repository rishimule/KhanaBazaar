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

## 1. Provision
```bash
export PROJECT_ID REGION=asia-south1 GH_REPO=rishimule/KhanaBazaar
export DB_PASSWORD="$(openssl rand -hex 16)"
bash deploy/gcp/bootstrap.sh
# Then enable PostGIS (the script prints the exact connect command):
gcloud sql connect kb-pg --user=postgres --database=khanabazaar
#   CREATE EXTENSION IF NOT EXISTS postgis;
#   CREATE EXTENSION IF NOT EXISTS postgis_topology;
# Replace the Maps key placeholders with real values:
echo -n "REAL_SERVER_KEY"  | gcloud secrets versions add gmaps-server-key  --data-file=-
echo -n "REAL_BROWSER_KEY" | gcloud secrets versions add gmaps-browser-key --data-file=-
```

## 2. Bootstrap images
```bash
export AR_HOST=asia-south1-docker.pkg.dev
gcloud auth configure-docker $AR_HOST --quiet
docker build -t $AR_HOST/$PROJECT_ID/kb/api:bootstrap -f backend/app/Dockerfile backend/app
docker push   $AR_HOST/$PROJECT_ID/kb/api:bootstrap
docker build -t $AR_HOST/$PROJECT_ID/kb/web:bootstrap \
  --build-arg NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY="REAL_BROWSER_KEY" \
  -f frontend/Dockerfile frontend
docker push   $AR_HOST/$PROJECT_ID/kb/web:bootstrap
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
gcloud run jobs create kb-seed --region=$REGION \
  --image=$AR_HOST/$PROJECT_ID/kb/api:bootstrap --service-account=$SA $COMMON_VPC \
  --set-env-vars=ENVIRONMENT=production,MEILI_URL=$MEILI_URL \
  --set-secrets=DATABASE_URL=database-url:latest,REDIS_URL=redis-url:latest,JWT_SECRET=jwt-secret:latest,OTP_PEPPER=otp-pepper:latest,MEILI_MASTER_KEY=meili-master-key:latest \
  --command=python --args=-m,app.db.dev_seed
gcloud run jobs execute kb-seed --region=$REGION --wait
```

## 5. Deploy api -> worker -> web
```bash
RUNTIME_SECRETS="JWT_SECRET=jwt-secret:latest,OTP_PEPPER=otp-pepper:latest,DATABASE_URL=database-url:latest,REDIS_URL=redis-url:latest,MEILI_MASTER_KEY=meili-master-key:latest,GOOGLE_MAPS_SERVER_API_KEY=gmaps-server-key:latest,DEV_LOGS_USERNAME=dev-logs-username:latest,DEV_LOGS_PASSWORD=dev-logs-password:latest"

# api
gcloud run deploy khanabazaar-api --region=$REGION \
  --image=$AR_HOST/$PROJECT_ID/kb/api:bootstrap --service-account=$SA $COMMON_VPC \
  --cpu=1 --memory=512Mi --min-instances=0 --max-instances=5 --concurrency=40 --port=8080 \
  --allow-unauthenticated \
  --set-env-vars=ENVIRONMENT=production,API_V1_STR=/api/v1,EMAIL_PROVIDER=console,SMS_PROVIDER=console,EXPOSE_DEV_OTPS=true,MEILI_URL=$MEILI_URL \
  --set-secrets=$RUNTIME_SECRETS
export API_URL=$(gcloud run services describe khanabazaar-api --region=$REGION --format='value(status.url)')

# worker (Celery + embedded beat; internal ingress; CPU always allocated)
gcloud run deploy khanabazaar-worker --region=$REGION \
  --image=$AR_HOST/$PROJECT_ID/kb/api:bootstrap --service-account=$SA $COMMON_VPC \
  --cpu=1 --memory=512Mi --no-cpu-throttling --min-instances=1 --max-instances=1 \
  --no-allow-unauthenticated --ingress=internal \
  --command=celery --args=-A,app.core.celery_app,worker,-B,--loglevel=info,--concurrency=2 \
  --set-env-vars=ENVIRONMENT=production,EMAIL_PROVIDER=console,SMS_PROVIDER=console,EXPOSE_DEV_OTPS=true,MEILI_URL=$MEILI_URL \
  --set-secrets=$RUNTIME_SECRETS

# web (API_INTERNAL_URL at runtime)
gcloud run deploy khanabazaar-web --region=$REGION \
  --image=$AR_HOST/$PROJECT_ID/kb/web:bootstrap --service-account=$SA \
  --cpu=1 --memory=512Mi --min-instances=0 --max-instances=5 --concurrency=80 --port=8080 \
  --allow-unauthenticated \
  --set-env-vars=API_INTERNAL_URL=$API_URL
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
  `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY`.
- Push to `release` -> CI builds, migrates, and updates the services.

## Teardown
`gcloud projects delete $PROJECT_ID` removes everything (stops all billing).
