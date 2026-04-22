# Gate `/stores` by Seller Approval — Design

**Date:** 2026-04-22
**Status:** Draft
**Scope:** Public store-discovery endpoints (`GET /stores/`, `GET /stores/{id}`, `GET /stores/{id}/inventory`) must only expose stores whose owning seller has an `Approved` `SellerProfile`. Existing seed stores get backfilled profiles so they keep appearing after the gate ships.

## Motivation

Today `GET /api/v1/stores/` only filters by `Store.is_active`. Any seller — including those without a `SellerProfile` entirely — can have their store publicly listed simply by posting to `POST /stores/`. This defeats the admin approval workflow: admins can reject a seller, but the seller's store stays visible to customers, and sellers who never applied are indistinguishable from verified ones.

The current observable symptom: `/admin/sellers` shows Sana Kapoor and Arjun Menon approved (both with `SellerProfile.verification_status = Approved`), yet `/stores` shows three stores owned by `seller@/seller2@/seller3@khanabazaar.dev` — seed test users who have no `SellerProfile` at all.

## Scope

In scope:

- Add a gate on the three public store-discovery endpoints: list, detail, public inventory.
- Backfill `SellerProfile` rows for the three seed seller accounts in `seed_database.py` so the three demo stores remain visible.
- Extend `tests/test_stores.py` to cover the visibility matrix.

Out of scope:

- `POST /stores/` pre-approval creation gate. Sellers can keep drafting stores while pending; the new public filter hides those drafts until approval.
- `/stores/my` and `/stores/{id}/inventory/all` filtering. These are seller-auth gated and must always show the seller's own data regardless of approval.
- Inventory mutation endpoints (`POST/PUT/DELETE .../inventory`). Seller-auth gate already handles ownership; approval is orthogonal.
- Cart/order implications. Carts are localStorage-only today per `CLAUDE.md`; rejected seller → hidden store → stale cart lines are left for a future order spec.

## Visibility Rule

A store is **publicly visible** when all three hold:

1. `Store.is_active = true`
2. A `SellerProfile` exists for `Store.seller_id` (join path: `Store.seller_id → User.id ← SellerProfile.user_id`).
3. `SellerProfile.verification_status = VerificationStatus.Approved`.

The relationship `SellerProfile.user_id` is already `unique=True`, so an `INNER JOIN` yields at most one profile per store. No schema change.

## Backend Changes

**File:** `backend/app/src/app/api/stores.py`

Add a small helper at module scope:

```python
from app.models.seller import SellerProfile, VerificationStatus


async def _get_approved_store_or_404(
    store_id: int, session: AsyncSession
) -> Store:
    stmt = (
        select(Store)
        .join(SellerProfile, SellerProfile.user_id == Store.seller_id)
        .where(
            Store.id == store_id,
            Store.is_active,
            SellerProfile.verification_status == VerificationStatus.Approved,
        )
    )
    result = await session.exec(stmt)
    store = result.first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store
```

Apply to the three public endpoints:

- `GET /stores/` — swap the current `select(Store).where(Store.is_active)` for the JOIN above (minus the `Store.id` predicate), preserving pagination.
- `GET /stores/{store_id}` — replace `session.get(Store, store_id)` with `_get_approved_store_or_404(store_id, session)`.
- `GET /stores/{store_id}/inventory` — call the same helper to check the store exists and is approved before returning inventory.

Unchanged:

- `GET /stores/my`, `GET /stores/{store_id}/inventory/all` — seller-auth paths, no approval filter.
- `POST /stores/`, inventory write endpoints — unchanged.

When an Approved seller is later rejected, the live query-time join reflects the change immediately: next `/stores/` call hides the seller's stores without any admin follow-up action.

## Seed Backfill

**File:** `backend/app/scripts/seed_database.py`

Add a `SEED_PROFILES` constant and a new step between "Inserting stores" and "Inserting inventory" (profiles are inserted before stores so ordering is flexible — the seed is idempotent). Each profile mirrors the matching store's structured address so the two stay consistent when an admin reviews the application.

```python
SEED_PROFILES = [
    {
        "seller_idx": 1,  # Ravi Sharma, seller@khanabazaar.dev
        "store_idx": 0,   # Sharma General Store
        "business_name": "Sharma General Store",
        "business_category": "Groceries",
        "phone": "+919812340001",
        "gst_number": "06AAACR5055K1Z3",
        "fssai_license": "10012022000001",
        "bank_account_number": "1234500000001",
        "bank_ifsc": "HDFC0000123",
    },
    {
        "seller_idx": 2,  # Krishna Patel, seller2@khanabazaar.dev
        "store_idx": 1,   # Krishna Supermart
        "business_name": "Krishna Supermart",
        "business_category": "Groceries",
        "phone": "+919812340002",
        "gst_number": "27AAACK8899L1Z7",
        "fssai_license": "10012022000002",
        "bank_account_number": "1234500000002",
        "bank_ifsc": "ICIC0000456",
    },
    {
        "seller_idx": 3,  # Balaji Ramaswamy, seller3@khanabazaar.dev
        "store_idx": 2,   # Balaji Fresh Market
        "business_name": "Balaji Fresh Market",
        "business_category": "Groceries",
        "phone": "+919812340003",
        "gst_number": "33AAACB7777M1Z9",
        "fssai_license": "10012022000003",
        "bank_account_number": "1234500000003",
        "bank_ifsc": "SBIN0000789",
    },
]
```

For each entry the seed reads the matching `STORES[store_idx]` dict and uses those nine address fields (`address_line1`, `address_line2`, `landmark`, `city`, `state`, `pincode`, `country`, `latitude`, `longitude`) when constructing the `SellerProfile`. `verification_status = VerificationStatus.Approved`.

Idempotent: before inserting, check `SellerProfile.user_id == user.id`; skip if one exists.

`seed_seller_applications.py` is unchanged — it already seeds Sana (Approved) and Vikram (Rejected) with structured addresses.

## Tests

**File:** `backend/app/tests/test_stores.py` — extend.

Add a factory helper at module scope:

```python
async def _seller_with_store(
    session: AsyncSession,
    email: str,
    profile_status: VerificationStatus | None,
) -> tuple[User, Store]:
    """Create a seller User, optional SellerProfile, and an active Store."""
    ...
```

New cases:

1. `test_stores_lists_only_approved_sellers_stores` — seed one Approved + one Pending + one Rejected + one no-profile seller each with a store; `GET /stores/` returns exactly one row (the Approved one).
2. `test_store_detail_hidden_for_pending_seller` — `GET /stores/{id}` returns 404 when owner is Pending.
3. `test_store_detail_hidden_for_rejected_seller` — 404 when Rejected.
4. `test_store_detail_hidden_for_no_profile_seller` — 404 when no profile.
5. `test_store_detail_visible_for_approved_seller` — 200 when Approved.
6. `test_public_inventory_hidden_for_unapproved_store` — `GET /stores/{id}/inventory` returns 404 when owner is not Approved.
7. `test_my_stores_unfiltered_for_pending_seller` — `GET /stores/my` still returns the seller's own stores even when their profile is Pending (regression guard for Q1 decision).

Existing test `test_get_store_by_id_returns_nested_address` in `tests/test_stores.py` today creates a store for `mock_seller` and fetches it via `GET /stores/{id}`. Under the new gate that GET would 404 because `mock_seller` has no `SellerProfile`. The fix: add a small fixture that seeds an Approved `SellerProfile` for `mock_seller` before any test that exercises public store visibility. `test_seller_can_create_store` (tests `POST`, not public `GET`) and `test_public_can_fetch_products_and_stores` (only asserts status 200, accepts empty list) continue to pass unchanged.

## Frontend Manual Verification

Per `CLAUDE.md` the repo has no automated frontend tests. Manual plan:

1. Fresh dev DB → `alembic upgrade head` → `seed_database.py` → `seed_seller_applications.py`.
2. `/stores` (unauthenticated or as customer) shows Sharma, Krishna, Balaji — nothing else.
3. Approve Sana via `/admin/sellers` → no change (she has no store yet).
4. Log in as `seller@khanabazaar.dev` → `/seller` dashboard lists Sharma General Store.
5. Navigate directly to `/stores/999` (nonexistent) → "Store Not Found" card from `stores/[id]/page.tsx:88-104`.
6. As admin, revoke Ravi Sharma's approval (reject with any reason) → reload `/stores` → Sharma General Store gone. `/stores/1` → "Store Not Found" card.
7. Re-approve → store reappears.

## Rollout

One PR, one deploy. Seed script change and backend gate ship together so the three demo stores' profiles exist before the gate goes live. No feature flag needed (pre-production).

## Open Questions

None. All decisions captured in the brainstorming transcript.
