# Structured Address Fields — Design

**Date:** 2026-04-22
**Status:** Draft
**Scope:** Replace single free-text `address` string on `SellerProfile` and `Store` with a structured 9-field address. Same shape reserved for a future customer delivery-address model.

## Motivation

The current schema stores seller and store addresses as a single `str` column. This makes it impossible to:

- Validate Indian postal codes.
- Filter or index by city/state/pincode.
- Feed a future delivery-radius or geocoding feature.
- Render clean structured views in the admin review modal.

Splitting into structured fields is a one-time schema break that unblocks all of the above.

## Scope

In scope:

- `SellerProfile.address` — seller business address (created during signup wizard).
- `Store.address` — per-store location address.
- Shared Pydantic/SQLModel `AddressBase` mixin reusable by a future customer delivery-address model.

Out of scope (separate specs):

- Pincode → city/state autofill (India Post API).
- Map picker / geocoding for lat/lng capture.
- Customer delivery-address model itself (only the shared shape is prepared here).

## Field Schema

All addresses share the following 9 fields, implemented as a mixin:

| Field            | Type            | Nullable | Constraints                                              |
|------------------|-----------------|----------|----------------------------------------------------------|
| `address_line1`  | `str`           | No       | 1–120 chars. Street / house / building.                  |
| `address_line2`  | `str \| None`   | Yes      | 0–120 chars. Apartment / floor / unit.                   |
| `landmark`       | `str \| None`   | Yes      | 0–120 chars. Free text.                                  |
| `city`           | `str`           | No       | 1–80 chars.                                              |
| `state`          | `str`           | No       | When `country == "India"`: must match one of 36 seeded Indian states/UTs. Otherwise free text, max 80 chars. |
| `pincode`        | `str`           | No       | When `country == "India"`: regex `^[1-9]\d{5}$`. Otherwise 3–10 chars. |
| `country`        | `str`           | No       | Default `"India"`. Max 60 chars.                         |
| `latitude`       | `float \| None` | Yes      | Range `-90.0 .. 90.0`.                                   |
| `longitude`      | `float \| None` | Yes      | Range `-180.0 .. 180.0`.                                 |

Validation lives on the `AddressBase` Pydantic model via `@field_validator` / `@model_validator`. State-list enforcement reads from a single source of truth (constants module).

## Backend

### Files

- `backend/app/src/app/core/indian_states.py` — module-level `INDIAN_STATES: list[str]` (28 states + 8 UTs, alphabetical).
- `backend/app/src/app/models/address.py` — `AddressBase` SQLModel mixin with the 9 columns plus validators. Imported by both `SellerProfile` and `Store`.
- `backend/app/src/app/schemas/address.py` — `AddressPayload` Pydantic model used by API request/response bodies. Same 9 fields, same validators.
- `backend/app/src/app/utils/address.py` — `format_address(addr) -> str` helper producing a single-line pretty string ("12 MG Road, Sector 14, Gurugram, Haryana 122001") for logs and admin one-liner displays.

### Model Changes

- `SellerProfile` — drop `address: str`, add the 9 columns via `AddressBase`.
- `Store` — drop `address: str`, add the 9 columns via `AddressBase`.

### API Changes

- `POST /api/v1/auth/seller/signup` — request body replaces flat `address: str` with `address: AddressPayload`. Response returns nested `address`.
- `GET /api/v1/sellers/me/profile` — returns `address: AddressPayload` nested.
- `PATCH /api/v1/sellers/me/profile` — when the `address` key is present in the request body, it is treated as a full replacement: the entire `AddressPayload` must be supplied and passes all field validators. There is no per-field address patch in v1 (other top-level profile fields outside `address` remain individually patchable as before).
- `POST /api/v1/stores` — body replaces flat `address` with structured.
- `GET /api/v1/stores`, `GET /api/v1/stores/{id}` — return nested `address`.
- Admin seller endpoints — return nested `address` in seller detail.
- **New:** `GET /api/v1/meta/indian-states` → `{"states": ["Andhra Pradesh", ...]}`. Public, no auth.

### Wire Format

DB columns stay flat (`address_line1`, `address_line2`, ... on the owner table). API serializers compose/decompose the nested `address` object. This keeps JSON clean without introducing a join.

## Frontend

### Shared Component

`frontend/src/components/AddressFields.tsx` + `AddressFields.module.css`.

Props:

```ts
interface AddressFieldsProps {
  value: Address;
  onChange: (next: Address) => void;
  errors?: Partial<Record<keyof Address, string>>;
  disabled?: boolean;
}
```

Layout:

- Line 1 (required) — text input.
- Line 2 (optional) — text input.
- Landmark (optional) — text input.
- City (required) — text input.
- State (required) — `<select>` populated from `/api/v1/meta/indian-states`.
- Pincode (required) — text input, `inputMode="numeric"`, `pattern="[1-9]\d{5}"`, maxLength 6.
- Country — read-only "India" for v1 (value still submitted).
- `latitude` / `longitude` — schema fields present in the TS type, **no UI in v1** (left null on submit). Reserved for a future map-picker spec.

State list is fetched once per app load and cached at module scope (`frontend/src/lib/indian-states.ts`), not per mount.

### Types

`frontend/src/types/index.ts`:

```ts
export interface Address {
  address_line1: string;
  address_line2: string | null;
  landmark: string | null;
  city: string;
  state: string;
  pincode: string;
  country: string;
  latitude: number | null;
  longitude: number | null;
}
```

`SellerProfile.address` and `Store.address` change from `string` to `Address`.

### Formatter

`frontend/src/lib/format-address.ts` — `formatAddress(addr: Address): string`. Mirrors backend output.

### Call Sites

- `app/seller/signup/page.tsx` — replace single textarea + `address: string` state with `<AddressFields>` and `address: Address` state. Review step renders the formatted single-line string.
- `app/admin/sellers/page.tsx` — review modal renders the structured block (each labelled row).
- `app/stores/page.tsx`, `app/stores/[id]/page.tsx` — render via `formatAddress`.
- `app/page.tsx`, `app/sell/page.tsx` — render via `formatAddress` wherever a store address is shown.
- `lib/mock-data.ts` — mock store rows updated to the structured shape.

## Migration

Pre-production; no live seller/store data to preserve.

Alembic revision `xxxx_split_address_fields.py`:

1. `op.execute("TRUNCATE sellerprofile, store RESTART IDENTITY CASCADE")` — wipes dev rows so the new NOT NULL columns can be added cleanly without placeholder defaults that would violate app-level validators (`address_line1` min length, pincode regex).
2. `op.drop_column("sellerprofile", "address")`.
3. `op.drop_column("store", "address")`.
4. Add the 9 columns to each table using the nullability specified in the field schema. Required columns are added as plain NOT NULL with no `server_default` — the preceding truncate guarantees no pre-existing rows.
5. `downgrade()` re-adds `address: str NOT NULL DEFAULT ''` on both tables. Downgrade is lossy: structured fields cannot be recombined into the original free-text address.

Migration docstring warns: this is a breaking schema change that truncates seller and store rows. It is only safe to run in pre-production environments.

Migration ordering: runs after `d6342a56eaf6_add_sellerprofile_table`.

## Testing

### Backend

- `tests/test_address_validator.py` — unit tests for `AddressPayload`:
  - Valid `110001` passes.
  - `023456` (leading zero) fails.
  - `12345` (5 digits) fails.
  - `abcdef` fails.
  - Non-India country (`"Nepal"`, pincode `"44600"`) passes (skips India regex).
  - `latitude = 91` fails.
  - `longitude = -181` fails.
  - State not in the 36-entry list fails.
- `tests/test_stores.py` — extend:
  - Create store with structured address → 201, response contains nested `address`.
  - Create store missing `address_line1` → 422.
  - `GET /stores/{id}` returns nested `address`.
- `tests/test_seller_register.py` — extend: signup through `POST /api/v1/auth/seller/signup` with a structured address succeeds and response contains nested `address`; signup missing a required address subfield returns 422.
- `tests/test_seller_status.py` — extend: `GET /api/v1/sellers/me/profile` returns nested `address`; `PATCH /api/v1/sellers/me/profile` with a full `AddressPayload` replaces the address; `PATCH` with a partial address object (missing a required subfield) returns 422.
- Fixture `make_address() -> dict` in `tests/conftest.py` returning a valid address dict.
- `tests/test_meta.py` — `GET /api/v1/meta/indian-states` returns 36 entries, contains "Maharashtra".

### Frontend

Repo has no automated frontend test infra (see `CLAUDE.md`). Manual test plan:

1. Seller signup wizard — fill all 9 visible fields, submit → seller created.
2. Enter invalid pincode (`023456`) → inline error, submit blocked.
3. State `<select>` populated from API (36 options).
4. Admin review modal shows each address field on its own row.
5. Store listing + detail show formatted single-line address.
6. `PATCH /sellers/me/profile` from profile-edit path updates city only (via full address replace) and persists.

### Quality Gates

- `uv run ruff check .` passes.
- `uv run mypy .` passes.
- `uv run pytest -v` passes.
- `npm run lint` passes.
- `npm run build` passes.

## Rollout

1. Merge migration + backend changes.
2. Merge frontend changes in the same PR (the API is breaking — no point staging).
3. Dev: run migration (truncate is performed by the migration itself), then re-signup a test seller.
4. No feature flag needed (pre-prod).

## Open Questions

None. All decisions captured in the brainstorming transcript for this spec.
