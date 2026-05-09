<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Seller Services & 1-Store-Per-Seller — Design Spec

**Date**: 2026-05-03
**Status**: Approved (brainstorming complete, ready for implementation plan)

## 1. Goal

Replace the free-text `SellerProfile.business_category` field with a structured many-to-many link from sellers to platform services (Grocery, Electronics, Pharmacy). Capture services during the "Become a seller" application flow. Enforce one store per seller and auto-provision the store on admin approval.

## 2. Decisions (locked)

| # | Decision | Rationale |
|---|---|---|
| Q1 | Replace `business_category` entirely with services list | `business_category` is unstructured free-text with no taxonomy. Service table is canonical. Drift risk if both kept. |
| Q2 | Services live on `SellerProfile` only (not on `Store`). Store inherits via owner profile. | 1:1 store↔profile makes per-store services redundant. Single source of truth. |
| Q3 | Services are **locked after approval** — only admin can change them | KYC-style gate. Admin certifies which services seller is approved for. |
| Q3a | (Moot due to Q4 — 1 store per seller) | — |
| Q4 | One store per seller, enforced by `UNIQUE (seller_profile_id)` on `store` | Simplifies model, matches user intent. |
| Q5 | Multi-select control = checkbox grid (one card per service) | Visible options at small N (3 services), scales to ~10. |
| Q6 | Admin approval auto-creates the Store (name = `business_name`, address = copy of business address) | Zero-friction post-approval. Reuses already-collected data. Matches existing seed shape. |

## 3. Data model

### New table: `sellerprofile_service`

```
sellerprofile_service
├── id (pk, int)
├── seller_profile_id (fk → sellerprofile.id, not null, indexed)
├── service_id (fk → service.id, not null, indexed)
├── created_at (timestamptz, not null)
├── updated_at (timestamptz, not null)
└── UNIQUE (seller_profile_id, service_id)  -- prevent duplicates
```

### Modified tables

- **`sellerprofile`**: drop column `business_category` (varchar, nullable)
- **`store`**: add `UNIQUE (seller_profile_id)` constraint

### Read pattern

`Store.services` resolved at query time via `Store → SellerProfile → SellerProfile.services` (junction join). No `store_service` table.

## 4. API surface

| Endpoint | Change | Auth |
|---|---|---|
| `POST /sellers/register` | Drop `business_category`. Add `service_ids: List[int]` (Pydantic `min_length=1`). | Email-OTP |
| `PATCH /sellers/me` | Drop `business_category`. Accept `service_ids` **only when** `verification_status != approved` (i.e. pending or rejected). Reject with 400 "Services are locked after approval" if seller is approved. | Seller |
| `GET /sellers/me` | Response drops `business_category`, adds `services: List[ServiceRead]`. | Seller |
| `GET /sellers/admin/applications` | Each application includes `services: List[ServiceRead]`. | Admin |
| `PATCH /sellers/admin/{seller_id}/services` | New. Body: `{service_ids: List[int]}` (min 1). Replaces seller's services atomically. | Admin |
| `POST /sellers/admin/{seller_id}/approve` | Side-effect: auto-create Store using `business_name` + copy of business address. Idempotent if store already exists. Rejects with 400 if services are empty. | Admin |
| `GET /stores/{id}` and `GET /stores` | Response includes `services: List[ServiceRead]` (resolved via owner profile). | Public |
| `GET /catalog/services` | Already shipped. Used by signup form. | Public |

### Validation rules

- `service_ids` must reference existing **active** services (else 400, message names the offending id)
- `service_ids` must be non-empty (Pydantic `min_length=1` → 422 on empty)
- `service_ids` deduped server-side before persisting
- Admin services-PATCH refuses empty list (400, "At least one service required")
- Approval refuses if profile has zero services (400, "Set services before approving")

## 5. Signup wizard (Step 4)

### Current step 4 ("Tell us about your business")

- Business name (text)
- Business category (text, free-form) ← **REMOVE**
- Business address (AddressFields)

### New step 4

- Business name (text)
- **Services offered** (checkbox grid, multi-select, min 1) ← **NEW**
- Business address (AddressFields)

### Services control

- Fetched from `GET /catalog/services` on step 4 mount (single fetch, cache for session)
- One card per service: emoji icon + name + description + checkbox
- Grid: 2 cols mobile / 3 cols desktop (responsive via CSS Modules)
- Validation: inline error "Select at least one service" if `serviceIds.length === 0` on Next
- State: `serviceIds: number[]` in component state
- Loading state: skeleton grid while fetching

### Step 6 ("Review")

Show services as comma-joined badge list (e.g. `[Grocery] [Pharmacy]`) next to existing fields.

### Resubmit flow (rejected applications)

- Pre-fill `serviceIds` from `GET /sellers/me` services
- Editable since not yet approved (rejected status implies not locked)

### Pending screen (`/seller/signup/pending`)

No change. Services not displayed.

## 6. Admin sellers review page

### Table column

- Replace "Business Category" → **"Services"**
- Render: badge list. Cap at 2 visible + `+N more` if longer.

### Detail panel

- Replace `business_category` row with **Services** row showing all service badges
- Pencil icon next to "Services" label opens inline edit popover (checkbox grid, same component as signup step 4)
- Save button → `PATCH /sellers/admin/{id}/services`
- Cancel discards
- Edit allowed in **all** statuses (pending, approved, rejected) — admin lock applies to *seller*, not admin

### Approval action

- Existing "Approve" button now also auto-creates Store atomically
- Toast: "Approved. Store provisioned."
- Approve button disabled (with tooltip) if services list empty — backend also enforces

### Filters

Existing pending/approved/rejected filter unchanged. Filter-by-service deferred (YAGNI).

## 7. Approval auto-creates Store

### Atomic transaction in `POST /sellers/admin/{seller_id}/approve`

1. Validate: profile.services count ≥ 1 (else 400)
2. Set `seller_profile.verification_status = approved`
3. Check existing Store by `seller_profile_id`:
   - **Present**: leave it (idempotent re-approval after rejection cycle, e.g. seller had a prior approval)
   - **Absent**: create Store with:
     - `name = seller_profile.business_name`
     - `address_id`: deep-copy a new Address row from business address (decouples future edits)
     - `is_active = True`
     - `seller_profile_id = seller_profile.id`
4. Commit

### Failure modes

- Unique constraint violation on `seller_profile_id` (race): swallow as success (idempotent)
- Missing services: 400 before any state change

### Rejection flow

`POST /sellers/admin/{seller_id}/reject` unchanged. No Store touched.

### Re-approval

Existing Store stays. Services may have changed (admin-edited during reject cycle). Inventory survives.

## 8. Migration

### Alembic up-migration `<rev>_add_seller_services_drop_business_category`

1. Create `sellerprofile_service` table with BaseSchema columns + FKs + unique constraint
2. Backfill: insert `(seller_profile.id, service.id WHERE slug='grocery')` for every existing `sellerprofile` (all current sellers are grocery — verified from seed data and dev DB)
3. Drop `sellerprofile.business_category` column
4. Add `UNIQUE (seller_profile_id)` on `store` table

### Alembic down-migration

1. Drop `UNIQUE` constraint on `store.seller_profile_id`
2. Re-add `business_category VARCHAR` (nullable)
3. Backfill `business_category = 'Groceries'` for all rows
4. Drop `sellerprofile_service`

### Dev seed updates (`dev_seed.py`)

- `STORE_OWNER_PROFILES` and `APPLICATIONS`: drop `business_category` field, add `service_slugs: ["grocery"]`
- `_upsert_seller_profile`: accept `service_slugs`, look up service ids, upsert junction rows
- `EXPECTED_FULL_COUNTS`: add `sellerprofile_service: 6`

## 9. Tests

### Backend

| File | New / changed tests |
|---|---|
| `test_seller_register.py` | Reject empty `service_ids` (422); reject invalid service_id (400); success with multi-service; resubmit (PATCH /sellers/me as rejected user) updates services; PATCH /sellers/me with service_ids on approved user → 400 |
| `test_admin_applications.py` | Admin PATCH services replaces set; admin PATCH rejects empty list (400); approve auto-creates Store; approve with empty services → 400; re-approval after rejection is idempotent (no duplicate store) |
| `test_admin_verify.py` | Update for store auto-creation assertions |
| `test_dev_seed.py` | Updated `EXPECTED_FULL_COUNTS` includes `sellerprofile_service: 6` |
| `test_stores.py` | Second store for same seller fails with 409; store response includes `services` array |
| `test_schema_reset_models.py` | `sellerprofile_service` table registered; `business_category` column absent |

### Frontend (manual smoke per CLAUDE.md — no FE test framework)

- Signup wizard step 4 renders services grid, blocks Next on empty selection, submits `service_ids`
- Step 6 review shows selected services
- Admin sellers table renders service badges
- Admin edit-services popover persists changes
- Approve action provisions Store (verify via `/seller` dashboard post-approval shows store ready)

## 10. Out of scope (explicit YAGNI)

- Filter customer storefront by service
- Per-store service subset (Q3a moot under 1:1)
- Admin "rename service / deactivate service" UI (use SQL ad hoc)
- Service icons (placeholder emoji until designer ships assets)
- Multi-store per seller (1:1 enforced)
- Free-form `tagline` field on profile

## 11. Open questions

None at design time. All gates resolved during brainstorming.
