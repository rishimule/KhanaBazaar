<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Local Reset and Canonical Seed Flow — Design

**Date:** 2026-04-24
**Status:** Draft
**Scope:** Local-development-only reset of Dockerized Postgres and Redis, followed by deterministic reseeding of the application's demo data.

## Motivation

Today the repo has two separate seed entrypoints:

- `backend/app/scripts/seed_database.py` creates users, categories, products, stores, and inventory.
- `backend/app/scripts/seed_seller_applications.py` creates seller-profile application data for the admin approval flow.

That split no longer matches the backend's behavior. Public store visibility now depends on `SellerProfile.verification_status`, but `seed_database.py` does not create `SellerProfile` rows for the sellers who own the three demo stores. A local database reset followed by only the "main" seed can therefore leave `/stores` in a misleading state.

Manual table truncation is also the wrong default for this repo. It is order-sensitive, easy to miss tables, and ignores Redis state such as OTP cooldown and rate-limit keys. Rebuilding a "new Docker image" is not necessary either: `docker-compose.yml` uses stock images (`postgres:15`, `redis:alpine`) and persists state in the named volumes `postgres_data` and `redis_data`. The reliable reset boundary is the volume layer, not the image layer.

## Goals

- Provide one canonical local reset flow that restores a known-good state from scratch.
- Remove dependence on manual `TRUNCATE` statements for everyday development resets.
- Clear both relational data and Redis application state in one operation.
- Seed enough deterministic data to exercise the main product flows: auth, admin review, seller stores, public catalog, and store inventory.
- Add explicit local-only guardrails so the reset cannot be pointed at a non-local environment by mistake.

## Out of Scope

- Any staging or production reset workflow.
- Preserving developer-created local data across resets.
- Randomized or large-volume fixture generation.
- Reworking the pytest test database setup; tests already use `drop_all/create_all` against `khanabazaar_test`.
- Seeding every table with non-empty data. Tables without active product usage may remain empty after reset as long as the canonical flows work.

## Options Considered

### 1. Manual table truncation plus ad hoc reseeding

Pros:

- Fast once the DB is already running.
- No Docker lifecycle involvement.

Cons:

- Easy to miss tables or truncate in the wrong order.
- Leaves Redis state behind unless a second manual step is remembered.
- Keeps the current seed split and the current possibility of reseeding into a partially broken app state.

### 2. Recreate Postgres container only

Pros:

- Simpler than manual truncation.
- Gives a clean relational database.

Cons:

- Incomplete for this app because Redis state survives.
- Recreating the container without dropping named volumes does not actually reset data.

### 3. Full local state reset via Docker volumes, then unified canonical seed

Pros:

- Cleanest and least ambiguous reset.
- Clears Postgres and Redis together.
- Produces deterministic IDs and row counts.
- Simplifies documentation and day-to-day developer workflow.

Cons:

- Slower than a narrow table-level reset.
- Intentionally destructive to all local app state.

**Recommendation:** option 3.

## Recommended Architecture

The reset flow should have two layers with one clear responsibility each.

### Layer 1: Root orchestration command

Add a repo-root shell entrypoint:

- `scripts/reset_local_state.sh`

This script owns cross-service orchestration only:

1. Validate prerequisites (`docker`, `docker compose`, `uv`).
2. Verify it is running in a local/dev context.
3. Stop and remove local Postgres and Redis containers and their named volumes.
4. Start fresh Postgres and Redis containers.
5. Wait for Postgres to accept connections.
6. Run Alembic migrations to `head`.
7. Run the canonical seed script.
8. Print a concise success summary with expected row counts and known demo accounts.

This script should use `set -euo pipefail` so it stops on the first failure instead of continuing into a half-reset state.

### Layer 2: Canonical backend seed script

Keep `backend/app/scripts/seed_database.py` as the canonical dataset entrypoint, but expand it so it fully represents the app's current flows.

It should seed, in this order:

1. users
2. seller profiles
3. categories
4. master products
5. stores
6. store inventory

`seed_seller_applications.py` should stop being a separate canonical path and become a thin compatibility wrapper that calls shared helper functions from `seed_database.py`. This preserves any existing developer muscle memory without keeping two independent datasets.

The important design decision is that there must be exactly one canonical local demo dataset, even if multiple entrypoints temporarily point at it.

## Canonical Seed Dataset

The local demo data should cover the main app states without becoming broad or random.

### Users

Create exactly these users:

- 1 admin
- 1 customer
- 3 approved sellers who each own one visible demo store
- 1 pending seller application
- 1 approved seller application without a store
- 1 rejected seller application

Expected total: `8` users.

### Seller profiles

Create:

- 3 approved `SellerProfile` rows for the three store-owning sellers from the existing marketplace seed
- 3 admin-review examples: pending, approved, rejected

Expected total: `6` seller profiles.

The three store-owning seller profiles should use the same structured address fields as their matching store rows so the admin-review data and store data stay internally consistent.

### Catalog

Keep the existing marketplace dataset:

- 4 categories
- 12 master products

Expected totals:

- `4` categories
- `12` master products

### Stores and inventory

Keep the existing three demo stores and their inventory mix:

- 3 stores
- 26 inventory rows

Expected totals:

- `3` stores
- `26` store inventory rows

### Tables intentionally left empty

The reset recreates all schema objects through Alembic, but not every table needs demo rows. For example, `item` can remain empty because it is not part of the current product flows. This avoids seeding dead or placeholder data just to satisfy the phrase "all tables."

## Reset Flow

The canonical local reset sequence is:

1. Ensure backend API and Celery worker are not running.
2. Run `docker compose down -v`.
3. Run `docker compose up -d postgres redis`.
4. Wait until Postgres accepts connections on the configured local database.
5. Run migrations from `backend/app`:
   `uv run alembic upgrade head`
6. Run the canonical seed from `backend/app`:
   `uv run python scripts/seed_database.py`
7. Print or verify the expected row counts:
   - users: `8`
   - sellerprofile: `6`
   - category: `4`
   - masterproduct: `12`
   - store: `3`
   - storeinventory: `26`

No manual SQL truncation step is needed in the normal path.

## Local Safety Guardrails

Because this flow is intentionally destructive, it must fail fast if the environment does not look local.

The reset command should refuse to run unless all of the following are true:

- `docker-compose.yml` exists in the repo root.
- `DATABASE_URL` points at local Postgres, or the script uses the known local compose defaults.
- `REDIS_URL` points at local Redis, or the script uses the known local compose defaults.
- the target Postgres database name is the local development database, not a staging or production name.

Practical interpretation for this repo:

- local Postgres host should be `localhost` or `127.0.0.1`
- local Redis host should be `localhost` or `127.0.0.1`
- database name should be `khanabazaar`

If any check fails, the script should exit with a short actionable message instead of prompting interactively.

## Error Handling

The flow should stop immediately on:

- missing Docker or `uv`
- failed `docker compose` commands
- Postgres readiness timeout
- Alembic migration failure
- seed failure

There should be no "best effort" continuation. A partial reset is worse than a loud failure because it looks clean while leaving the repo in an inconsistent state.

The seed script should remain idempotent even though the reset starts from an empty database. That keeps direct `uv run python scripts/seed_database.py` usable for targeted local reseeding after schema-only changes.

## Verification

Verification should happen at two levels.

### Automated reset verification

At the end of the reset command, verify that the seeded row counts match the canonical dataset:

- users: `8`
- sellerprofile: `6`
- category: `4`
- masterproduct: `12`
- store: `3`
- storeinventory: `26`

If counts do not match, the reset command should exit non-zero.

### Manual product smoke checks

After the reset succeeds, the documented manual checks are:

1. Start the backend and frontend normally.
2. Visit the public store list and confirm the three demo stores appear.
3. Open one public store inventory page and confirm products render.
4. Sign in as the admin and confirm pending, approved, and rejected seller applications exist.
5. Request an OTP for a known seeded user and confirm the auth flow still works.

These are intentionally small checks; the goal is to prove the reset restored the main development flows, not to exhaustively test the app.

## Documentation Changes

Update `docs/local_setup.md` so the default reset path is the new command rather than manual table cleanup or one-off seed commands.

The docs should explicitly state:

- the reset is local-only
- it deletes Docker volumes for Postgres and Redis
- it does not require rebuilding images
- `seed_database.py` is the canonical dataset entrypoint

## Rollout Strategy

Ship this as one focused change:

1. add the reset orchestration command
2. unify the seed dataset
3. update local setup docs

This avoids an intermediate state where the repo documents one reset flow but still depends on split seeds.

## Open Questions

None. The design intentionally chooses the destructive full-volume reset as the default local workflow and treats manual truncation as a fallback-only technique, not the primary path.
