<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Handover guide

For the team taking over development and operations of **Sarvaka** (codebase
name: *Khana Bazaar*). Start here. This guide points you to the detailed docs
rather than repeating them.

> **This repository is public.** Credentials, account details and the open
> security notes are in a separate private file, `secrets/HANDOVER_SECRETS.md`.
> It comes to you outside Git, together with the design-docs bundle
> `secrets/design-docs-2026-10-11.tar.gz`. `secrets/` is gitignored; keep it that
> way, and never paste a credential into an issue, a PR or a commit.

## 1. Your first week, in this order

| # | Do this | Why |
|---|---|---|
| 1 | Get Owner on the GCP project `sarvaka-prod` and **link it to your own billing account** | The current billing account may be on a GCP Free Trial that ends around **2026-12-01**. An un-upgraded trial stops every resource, then deletes it 30 days later. The budget alert does not move with the project, so create your own. Private file §2 |
| 2 | Read the private notes and act on the security items first | Private file §1 |
| 3 | Take over the GitHub repo, then re-point deploy authentication | Deploys trust the repo *name*. A transfer or rename breaks them until you update Workload Identity Federation (§6.5) |
| 4 | Run the stack locally | §3 |
| 5 | Merge a trivial PR and watch it deploy | Proves you can ship and verify (§6) |
| 6 | Remove the previous owner's access and rotate every secret | Private file §8 |

## 2. The product in one minute

- **What it is:** a multi-vendor, hyperlocal marketplace for India, like Instacart.
  - Admins curate a multilingual master catalog (en, hi, mr, gu, pa).
  - Sellers apply, get approved, and run one store with several services
    (Grocery, Food, Pharmacy…), setting their own stock and prices.
  - Customers check out once per store and service. They pay by UPI, bank
    transfer, cash on delivery, pay-at-store or postpaid credit.
  - Long-distance courier orders, returns, and frozen order receipts are built in.
- **Names:**
  - **Sarvaka** is the live brand. It is set at runtime by `COMPANY_NAME` and at
    build time by `NEXT_PUBLIC_COMPANY_NAME`.
  - The code defaults to *Khanabazaar*.
  - Cloud resources keep their original `khanabazaar-*` / `kb-*` names on
    purpose; renaming them is all cost and no benefit (`deploy/gcp/README.md`).
- **Status:** live at **https://app.sarvakaecommerce.com**, deliberately in a
  **demo posture**:
  - `ENVIRONMENT=development`, so the dev mailbox at `/dev-emails` is on.
  - Phone-OTP checks are switched off, because no SMS plan has been bought.
  - Email goes out through Brevo.
  - The steps to a real launch are in
    [`docs/gcp_deployment.md`](docs/gcp_deployment.md#real-launch-checklist-out-of-scope-for-the-mvp).
- **Stack:**
  - Backend: FastAPI (Python 3.12, async SQLModel + Alembic), PostgreSQL 15 +
    PostGIS, Redis 7 + Celery, Meilisearch 1.11.
  - Frontend: Next.js 16 (App Router, React 19, CSS Modules, next-intl).
  - Hosting: Google Cloud.
- **The best single reference is [`CLAUDE.md`](CLAUDE.md).** Despite the name, it
  is the most complete and current engineering doc. It covers architecture, every
  feature's invariants, env vars and gotchas. Keep it up to date as you change
  things; `AGENTS.md` just points to it. Other docs:
  - [`README.md`](README.md)
  - [`docs/architecture.md`](docs/architecture.md), [`docs/flows.md`](docs/flows.md)
  - [`docs/development_guide.md`](docs/development_guide.md)
  - [`docs/courier_delivery.md`](docs/courier_delivery.md)
  - [`DESIGN.md`](DESIGN.md) (UI design system)

## 3. Run it locally (about 30 minutes)

You need Python 3.12 + [`uv`](https://docs.astral.sh/uv/), Node.js 20+ (CI uses
22), and either Docker or the Docker-free stack. Non-engineers on Windows can
follow [`docs/teammate-guide/`](docs/teammate-guide/README.md) instead.

```bash
git clone https://github.com/rishimule/KhanaBazaar.git && cd KhanaBazaar   # or its new home

# 1. Env files. Paste the ready-made ones from the private file §6, or start from the examples:
cp backend/app/.env.example backend/app/.env
cp frontend/.env.example frontend/.env.local

# 2. Postgres + PostGIS, Redis, Meilisearch
docker compose up -d            # no Docker? ./scripts/native_infra.sh setup (user space, no root)

# 3. Backend: dependencies, schema, demo data + search index
cd backend/app && uv sync && uv run alembic upgrade head && uv run python scripts/seed_database.py && cd ../..

# 4. Frontend dependencies
cd frontend && npm install && cd ..

# 5. Start everything: api :8000, Celery worker, web :3000, log viewer :8001
./scripts/dev.sh start          # also: status | logs backend | stop [--all] | restart | reset | start --tunnel
```

**Log in** at http://localhost:3000/login with a seeded email:

| Role | Email |
|---|---|
| Admin | `admin@khanabazaar.dev` |
| Seller | `seller@khanabazaar.dev` (`seller2@` … `seller9@` also exist) |
| Customer | `customer@khanabazaar.dev` |

Login is by emailed code only; there are no passwords. With `EMAIL_PROVIDER=console`,
the code appears in `./scripts/dev.sh logs backend`. If `DEV_INBOX_USER` and
`DEV_INBOX_PASSWORD` are set, it also shows at http://localhost:3000/dev-emails.
On a fresh seed, seeded accounts usually see a *"We've updated our policies"*
dialog first. That's expected; accept it locally.

**Tests** (backend only; the frontend has none):

```bash
docker compose exec postgres createdb -U postgres khanabazaar_test   # once
docker compose --profile test up -d meilisearch-test                 # test search on :7701
cd backend/app
COMPANY_NAME=Khanabazaar EMAIL_BRAND_NAME=Khanabazaar REDIS_URL=redis://localhost:6379/1 \
  uv run pytest -q > /tmp/pytest.log 2>&1; tail -3 /tmp/pytest.log
uv run ruff check . && uv run mypy .        # frontend: npm run lint && npx tsc --noEmit
```

The full suite takes 40–60 minutes; read §8 before your first run. Without
Docker, start the test search instance with `./scripts/native_infra.sh up --with-test`.
More detail: [`docs/local_setup.md`](docs/local_setup.md).

## 4. Find your way around

| Path | What's there |
|---|---|
| `backend/app/src/app/api/` | FastAPI routers. All are under `/api/v1`, mounted in `api/__init__.py` |
| `backend/app/src/app/services/` | Business logic. Routers stay thin |
| `backend/app/src/app/models/`, `backend/app/migrations/` | SQLModel tables and Alembic history. `schema.sql` (repo root) is a snapshot of head |
| `backend/app/src/app/worker.py`, `core/celery_app.py` | Celery tasks: email, SMS, WhatsApp, push, search sync, hourly sweeps |
| `backend/app/src/app/search/` | Meilisearch indexes, sync hooks, reindex CLI |
| `backend/app/tests/` | Pytest against a real Postgres test DB |
| `frontend/src/app/` | Next.js routes: `(customer)/[locale]/…` (localized storefront) and `(operator)/…` (seller, admin) |
| `frontend/src/lib/`, `components/` | API client, auth/cart contexts, shared UI |
| `frontend/messages/*.json` | UI copy for all 5 locales |
| `deploy/gcp/`, `.github/workflows/` | Infrastructure scripts, runbook, CI/CD |

Several rules deliberately live in exactly **one** place. Change them there and
nowhere else:

| Rule | Its one home |
|---|---|
| Which payment methods a store accepts, and the payee details | `services/payment_methods.py` |
| Delivery radius and local/courier zones | `services/serviceability.py` |
| Courier order state machine, and when a refund is owed | `services/courier_rules.py` |
| Order receipts (the only writer) | `services/receipts.py` |
| Customer account status changes | `services/account_lifecycle.py` |
| Admin audit rows, written in the same transaction as the change | `services/admin_audit.py` |
| Courier rules in the UI | `frontend/src/lib/courier.ts` |

## 5. How work gets done

- **Git:**
  - Branch off `main` (`feat/`, `fix/`, `chore/`, `docs/` …).
  - Use Conventional Commits.
  - Merge with a merge commit (`gh pr merge --merge`), and keep merged branches.
  - **A merge to `main` deploys to production.** `main` has no branch protection
    today; turn it on.
- **CI checks lint only:** Ruff (enforced), Mypy (advisory), ESLint and `tsc`.
  **Pytest is not in CI.** Run the suite locally before merging anything
  non-trivial.
- **Migrations:**
  - Let `uv run alembic revision --autogenerate -m "…"` generate the revision id.
    The history contains hand-written ids, so an invented one can collide and make
    every Alembic command fail with *"Cycle is detected"*.
  - Keep a single head (`uv run alembic heads`).
  - Regenerate `schema.sql` when the head changes.
  - Migrations must be backward compatible for one release (§6.1).
- **i18n:**
  - Customer pages are localized by URL prefix (`/hi/…`). Add copy to **all five**
    `frontend/messages/*.json` files.
  - Operator pages (seller and admin) have no URL prefix. Their language comes
    from the `__session` cookie: Firebase Hosting forwards no other cookie, which
    `CLAUDE.md` explains.
  - A new top-level route that is *not* localized must be listed in
    `frontend/src/i18n/unsupported-routes.ts`. Otherwise it builds fine and then
    404s in the browser.
- **Styling:** design tokens in `frontend/src/styles/design-tokens.css` plus CSS
  Modules. There is no Tailwind; keep it that way.
- **Design docs:**
  - About 130 design specs, implementation plans and audits are in the private
    bundle. `CLAUDE.md` cites many of them by path. They were never committed,
    because `docs/superpowers/` is gitignored.
  - From the repo root, run `tar -xzf secrets/design-docs-2026-10-11.tar.gz` so
    those paths resolve. Keep the archive inside `secrets/`: a copy anywhere else
    in the repo is not ignored.
  - Some docs that are cited were lost before the handover and are not in the
    bundle:
    - from `CLAUDE.md`: the specs for geo/delivery radius, the admin seller
      supervisor, and the seller phone-change OTP. Their rules survive in
      `CLAUDE.md`.
    - from `deploy/gcp/README.md`: the 2026-09-02 project-migration plan (which
      held the Cloud Build config for building the web image without Docker) and
      the 2026-09-12 custom-domain spec.
- **AI tooling (optional):** the repo is set up for Claude Code. `CLAUDE.md` holds
  the instructions, `.claude/` holds agents and commands (`/dev` drives
  `scripts/dev.sh`), and `.claude/docs/architectural_patterns.md` documents the
  patterns. The previous owner's private assistant notes don't transfer; what was
  useful in them is folded into §8.

## 6. Deploying

### 6.1 What a merge to `main` does

`.github/workflows/deploy.yml` runs one deploy at a time, takes 7–10 minutes and
is capped at 20:

1. **Build and push** `kb/api` and `kb/web` images to Artifact Registry. The web
   build bakes in the brand, the Maps browser key and the Web Push public key, so
   changing any of them needs a new build.
2. **Migrate.** The Cloud Run Job `kb-migrate` runs
   `backend/app/scripts/deploy_release.sh`:
   - ensure PostGIS;
   - `alembic upgrade head`;
   - idempotent backfills, and seeding of the policy documents;
   - seeding of demo data, but **only if the catalog is empty**;
   - a full Meilisearch reindex.
3. **Roll out** `khanabazaar-api`, which also re-pins a few env vars (§6.3), then
   `khanabazaar-web`.
4. **Deploy Firebase Hosting** for the custom domain. This step is non-fatal (§6.2).
5. **Restart the Celery worker** on the VM `kb-svc` over IAP SSH, and prune old
   images.

Consequences:
- The migration runs while the **old** api, web and worker are still serving, and
  the worker restarts last. So every schema change must work with the previous
  release's code.
- During that window, the old worker drops a Celery task enqueued under a
  **brand-new task name**. Reuse an existing name, or ship the worker change first.
- Rollbacks never undo a migration.

### 6.2 After every deploy

```bash
gh run list --workflow=deploy.yml --limit 3
gh run view <RUN_ID> --log | grep -i 'Deploy Firebase Hosting' | tail -20   # a green run can hide a failed Hosting step
curl -s https://app.sarvakaecommerce.com/api/v1/meta/health                    # always "ok": proves only that the api is up
curl -s "https://app.sarvakaecommerce.com/api/v1/search/suggest?q=milk" | head -c 300   # exercises Meilisearch on the VM
gcloud compute instances list --project=sarvaka-prod                          # kb-svc must be RUNNING
```

- **Image push fails** with *"Unable to retrieve Identity Pool subject token"*:
  it's a transient GitHub OIDC timeout and nothing has deployed yet. Run
  `gh run rerun <RUN_ID> --failed`.
- **The Migrate step fails:** check that `kb-svc` is running before anything else
  (§7.2). The real traceback is in the job's Cloud Logging entries, not the GitHub
  log.

### 6.3 Where production config lives

| Kind | Where | How to change it |
|---|---|---|
| `COMPANY_NAME`, `EMAIL_FRONTEND_BASE_URL`, `EMAIL_PROVIDER`, `PHONE_OTP_ENABLED` | Pinned in `deploy.yml` on every deploy | Edit `deploy.yml`. A console edit is reverted by the next deploy |
| `BREVO_FROM_EMAIL` | GitHub repo variable, applied by `deploy.yml` | Change the variable, then redeploy |
| Other api env vars (`ENVIRONMENT`, `FRONTEND_ORIGIN`, `IMAGE_STORAGE_BACKEND`, `GCS_*`, …) | The Cloud Run service | `gcloud run services update khanabazaar-api --region=asia-south1 --project=sarvaka-prod --update-env-vars=…`. A value that contains commas, like `FRONTEND_ORIGIN`, needs gcloud's delimiter syntax: `--update-env-vars=^@^FRONTEND_ORIGIN=https://a,https://b` |
| Secrets (12 in Secret Manager, 11 of them mounted on the api; `redis-password` is used only by the VM) | Secret Manager, mounted as `:latest` | Add a version, then roll out a new api revision. A value the worker also holds must be changed in `/opt/kb/.env` too |
| Web build-time values | GitHub repo secrets and variables, plus the `deploy.yml` build args | Change them, then redeploy |
| Worker env vars | `/opt/kb/.env` on `kb-svc`. **Deploys never rewrite it** | Edit by hand, then `sudo docker compose up -d --no-deps --force-recreate worker`. See "Redeploy" in [`deploy/gcp/README.md`](deploy/gcp/README.md) |

### 6.4 Rollback

```bash
gcloud run revisions list --service=khanabazaar-api --region=asia-south1 --project=sarvaka-prod
gcloud run services update-traffic khanabazaar-api --region=asia-south1 --project=sarvaka-prod --to-revisions=<REVISION>=100
```

- Roll back `khanabazaar-web` too whenever a change touched both.
- **After the fix-forward deploy, run `update-traffic … --to-latest`.** While
  traffic is pinned to an old revision, new deploys create revisions that receive
  no traffic. Don't run it before the fix is deployed, or it sends traffic straight
  back to the bad revision.
- For the worker, set `API_IMAGE=…/kb/api:<old-sha>` in `/opt/kb/.env` and
  recreate it. Put `:latest` back once you've fixed forward.

### 6.5 If the GitHub repository moves or is renamed

GitHub Actions authenticates to GCP through Workload Identity Federation. There
is no JSON key, and the trust is pinned to `rishimule/KhanaBazaar`. After the
transfer, run:

```bash
NEW=neworg/newrepo
gcloud iam workload-identity-pools providers update-oidc gh-provider --location=global \
  --workload-identity-pool=gh-pool --project=sarvaka-prod \
  --attribute-condition="assertion.repository=='$NEW'"
gcloud iam service-accounts add-iam-policy-binding gh-deployer@sarvaka-prod.iam.gserviceaccount.com \
  --project=sarvaka-prod --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/382925487269/locations/global/workloadIdentityPools/gh-pool/attribute.repository/$NEW"
```

Then check the repository's Actions secrets and variables, and re-create any
that didn't move (values in private file §4). Once a deploy succeeds, remove the
old binding with `remove-iam-policy-binding` and the old repo name.

### 6.6 Moving to a different GCP project

[`deploy/gcp/README.md`](deploy/gcp/README.md) is the runbook: `bootstrap.sh`,
then the VM, a two-pass first deploy, GitHub wiring, and the custom domain. Plan
for three things:

- **Data:** use `gcloud sql export sql` and import into the new instance.
  Meilisearch rebuilds itself from the database (the deploy runs a reindex).
- **Images:** product and avatar URLs are stored **absolute**
  (`https://storage.googleapis.com/<bucket>/…`). New bucket names therefore mean
  rewriting those rows, or keeping the old buckets readable.
- **DNS:** add only the `app` record at GoDaddy. **Never edit the apex or `www`
  records of `sarvakaecommerce.com`**: they serve a different project's live
  website.

## 7. Running production

### 7.1 What runs where (project `sarvaka-prod`, region `asia-south1`)

| Component | Resource |
|---|---|
| Web (Next.js) | Cloud Run `khanabazaar-web` (min 1, max 2), behind Firebase Hosting at `app.sarvakaecommerce.com` |
| API (FastAPI) | Cloud Run `khanabazaar-api` (min 1, max 3). The browser reaches it through the web app's `/api/v1` rewrite |
| Migrations + seed + reindex | Cloud Run Job `kb-migrate` |
| Celery worker + beat, Redis, Meilisearch, Cloud SQL proxy | e2-small VM `kb-svc` (zone `asia-south1-a`, internal IP `10.10.0.2`), run with Docker Compose from `/opt/kb` |
| Database | Cloud SQL `kb-pg` (PostgreSQL 15 + PostGIS, `db-f1-micro`); no authorized networks, so access is only via the connector or proxy |
| Files | Buckets `kb-product-images-sarvaka-prod` and `kb-user-media-sarvaka-prod` (public-read); `kb-db-backups-sarvaka-prod` (private) |
| Images, secrets | Artifact Registry repo `kb`; Secret Manager (12 secrets) |
| Email | Brevo, via raw HTTP calls. **Both** the api (login codes) and the worker (everything else) send |

When testing off-domain, use `https://khanabazaar-web-382925487269.asia-south1.run.app`.
It is the only `*.run.app` form on the CORS and Maps allow-lists; the form
`gcloud` prints is not on them.

### 7.2 Health, logs, incidents

- **`/health` is shallow.** It returns `ok` even when Redis, Meilisearch and the
  worker are all down. In September 2026, Google stopped `kb-svc` and it sat
  unnoticed for two days:
  - search returned nothing;
  - login codes, rate limits and background email were dead;
  - every deploy failed at the reindex step.

  Recovery: `gcloud compute instances start kb-svc --zone=asia-south1-a
  --project=sarvaka-prod`. The containers come back by themselves; then re-run the
  failed deploy. Adding a deep health check plus uptime alerting is high on the
  to-do list.
- **Logs:**
  ```bash
  gcloud run services logs read khanabazaar-api --region=asia-south1 --project=sarvaka-prod --limit=200
  gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="kb-migrate"' --project=sarvaka-prod --limit=100 --format='value(timestamp,textPayload)'
  gcloud compute ssh kb-svc --zone=asia-south1-a --tunnel-through-iap --project=sarvaka-prod \
    --command='cd /opt/kb && sudo docker compose ps && sudo docker compose logs --tail=100 worker'
  ```
  On the VM, Redis and Meilisearch listen on `10.10.0.2`, not on localhost.
  `redis-cli ping` answering `NOAUTH` means Redis is healthy.
- **Email goes missing silently.** `EMAIL_PROVIDER=brevo+console` swallows Brevo
  errors on purpose, and still records each message at `/dev-emails`. Search the
  api and worker logs case-insensitively for `send failed`. Keep Brevo's
  *Authorised IPs* feature **off**: production has no fixed egress IP.
- **Admin access to production:** see private file §1b.

### 7.3 Backups and cost

- Cloud SQL **automated daily backups are on** (21:00 UTC, 7 kept). Point-in-time
  recovery is off. The one-off SQL export from before a big migration is in
  `gs://kb-db-backups-sarvaka-prod`. Backups die with the instance and the
  project, so keep an off-project copy before any risky change.
- Production costs roughly **US$50–60 a month** at list prices. Today's ₹20,000
  budget alert belongs to the current billing account and does not move with the
  project, so set up your own after re-linking billing. The cheapest saving is
  running the web service at `min=0`.

## 8. Gotchas that each cost someone a day

**Tests**
- **Run only one pytest process per machine.** Runs share state:
  - the `khanabazaar_test` database, whose schema is dropped for each test;
  - the Redis db, which is flushed for each test;
  - the test Meilisearch indexes, which are wiped for each test;
  - the dev database, which worker tasks write to.

  A second concurrent run needs its own `KB_TEST_DB`, `DATABASE_URL` (migrated to
  head), `REDIS_URL` db, and `MEILI_TEST_URL` / `MEILI_TEST_KEY`.
- Pytest **flushes the Redis database named in `REDIS_URL`** before every test.
  That breaks a running dev stack (login codes "expire"). Run tests with
  `REDIS_URL=redis://localhost:6379/1`.
- Without the test Meilisearch on `:7701`, dozens of tests error out.
- Email tests assume the default brand, `Khanabazaar`. Either of these in your
  `.env` makes a few of them fail:
  - `COMPANY_NAME=Sarvaka`;
  - `.env.example`'s `EMAIL_BRAND_NAME="Khana Bazaar"`.

  That's why the §3 command overrides both. CI doesn't run pytest, so nothing
  else catches this.
- Celery email tasks build their own database engine from `DATABASE_URL`, so
  under test they query your **dev** database. Migrate it before trusting
  `test_order_emails.py`.
- `test_metrics.py` fails 2–4 tests depending on the IST clock and the day of the
  month. If only those fail, compare against `main` at the same moment.
- Never pipe pytest into `tail` (you get `tail`'s exit code); redirect to a file.
- Run mypy as `--no-incremental` when comparing results. Single-file runs on
  `tests/` poison the cache.
- In fixtures, save and restore `app.dependency_overrides`; never `pop` the global
  `get_redis` override.

**Local development**
- A freshly migrated empty database has no `language` rows, so the first signup
  returns 500. Run the seed.
- The seed enqueues about 10,000 search-sync tasks on Redis db 0, and any worker
  drains them before real work.
- `NEXT_PUBLIC_API_URL` must be set to an **explicit empty string**. Otherwise the
  browser calls `:8000` directly and gets "Network error".
- `next dev` sometimes serves the old bundle on the first reload after an edit.
  Reload again before you re-debug.
- Email templates use Jinja `StrictUndefined` with `trim_blocks`:
  - guard new variables with `is defined`;
  - render both branches of a new `{% if %}`.
- In client components, format dates with `toLocaleString` or an explicit
  `timeZone`. `useFormatter().dateTime` uses the *server's* zone, which is UTC on
  Cloud Run.

**Deploy and production**
- A **green deploy run does not prove Firebase Hosting deployed.** That step is
  `continue-on-error`, so read its log.
- Firebase Hosting **caches failure pages**: a 404 from a not-yet-deployed
  endpoint, or "Site Not Found" during certificate setup. Try `?cachebust=1`
  before debugging DNS or code.
- The Firebase Hosting hop adds about 300 ms per request from India. A free fix
  has been identified: build the web app with an absolute `NEXT_PUBLIC_API_URL`
  pointing at the api.
- Worker-only env vars must be added to `/opt/kb/.env` by hand (§6.3).

## 9. Open work, and decisions already made

**Open:**
- The private file §1 security items.
- **Real-launch hardening**
  ([`docs/gcp_deployment.md`](docs/gcp_deployment.md#real-launch-checklist-out-of-scope-for-the-mvp)):
  - production posture: `ENVIRONMENT=production`, dev mailbox off;
  - an SMS/WhatsApp provider, then re-enabling phone OTP (the cutover order there
    matters);
  - a static egress IP for the Maps server key;
  - observability (OpenTelemetry / Cloud Trace);
  - secret rotation.
- **Monitoring:** the only alert is the budget alert, and `/health` doesn't probe
  dependencies.
- **Worker restart in `deploy.yml`:** it runs `docker compose up -d worker`
  without `--no-deps`, which the runbook warns against. If `/opt/kb/.env` were ever
  damaged, a deploy could recreate Redis without its password. Add `--no-deps`.
- **Product follow-ups** in [`TODO.md`](TODO.md):
  - returns: an admin "initiate on behalf" screen; seller notifications; WhatsApp
    template IDs. Return windows default to 0, so the feature stays dark until
    sellers set one.
  - payment-gateway integration (Razorpay);
  - PWA icons still in the old colours, and a contrast fix.

**Decided:** reopen these only with new information.
- **Moving to Supabase, Cloudflare R2 or Firebase App Hosting was evaluated
  (September and October 2026) and rejected.**
  - Firebase can't host the API or worker, and App Hosting has no Mumbai region.
  - Supabase costs more at production grade and adds latency per query.
  - R2 saves nothing at today's media volume.
- **The worker, Redis and Meilisearch share one VM** instead of running on Cloud
  Run, for cost.
- **Production runs `ENVIRONMENT=development` on purpose** until the real launch.
- **Cloud resource names stay `khanabazaar-*`.**

## 10. Contacts

- Previous owner: Rishi Mule. *(Add preferred contact details and the support
  window for questions after the handover.)*
