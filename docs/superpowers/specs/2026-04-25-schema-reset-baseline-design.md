<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Schema Reset Baseline Design

Date: 2026-04-25
Status: Draft
Scope: Replace the current development schema with a clean baseline modeled on `new_schema.sql`, preserving current application flows while preparing future cart, order, payment, delivery, review, favorite, and multilingual catalog features.

## Decision

Use a destructive local/dev reset instead of a data-preserving migration. The database is still pre-production, and the requested direction is to reset rather than preserve existing rows. This keeps the implementation simpler, avoids brittle cross-shape data transforms, and lets the codebase converge directly on the target schema.

`new_schema.sql` is the source intent, not a file to run as-is. The implementation must translate it into SQLModel models and Alembic DDL, correcting invalid or incomplete SQL details along the way.

## Goals

- Create one coherent schema baseline that matches the intended product model.
- Keep existing auth, seller onboarding, admin review, store browsing, catalog, and inventory flows working.
- Normalize addresses into a shared `address` table.
- Separate user identity from role-specific profile data.
- Add multilingual catalog structure without forcing the frontend to expose translation management immediately.
- Add future-ready transactional tables for carts, orders, payments, delivery, reviews, and favorites.
- Refresh canonical dev seed data for the new table shape.

## Non-Goals

- Preserve existing local/dev database rows.
- Implement full checkout, payment gateway integration, delivery tracking UI, reviews, favorites, or translation-management UI in this change.
- Build production online migration steps.
- Change the frontend design unless needed to keep existing screens working against the updated API.

## DDL Corrections Required

Before generating the final migration, normalize the proposed schema:

- Add explicit PostgreSQL enum creation for `languagecode`, `userrole`, `verificationstatus`, `orderstatus`, `paymentmethod`, `paymentstatus`, and `deliverystatus`.
- Use valid SQLAlchemy/PostgreSQL types instead of quoted pseudo-types:
  - `TIMESTAMPTZ` as `sa.DateTime(timezone=True)`.
  - `VARCHAR(20)` as `sa.String(length=20)`.
  - `DOUBLEPRECISION` as `sa.Float()` or `sa.Double()` if the project standardizes on SQLAlchemy 2's explicit double type.
- Use lowercase enum values for app-facing enums where current code already depends on `.value`, especially `userrole` values: `customer`, `seller`, `admin`.
- Add explicit check constraints that are only comments in `new_schema.sql`, including review target exclusivity and optional domain checks.
- Add the partial unique index for one default customer address per profile.
- Avoid using raw quoted reserved identifiers where SQLModel/Alembic can manage quoting, while keeping table names such as `user` and `order` compatible with PostgreSQL.

## Intentional Compatibility Additions

Keep these fields even though they are not present in `new_schema.sql`, because current user-visible flows and tests depend on them:

- `sellerprofile.business_category`: used by seller signup and admin seller review. Keep it as a required current-flow field until seller onboarding is redesigned around `service` or catalog vertical selection.
- `masterproduct.base_price`: used by admin product management and seller inventory defaults. Keep it as the platform's suggested/default price while actual selling price remains `storeinventory.price`.

These additions should be documented in model comments or migration comments as compatibility fields so a future catalog/seller-onboarding redesign can remove or rename them intentionally.

## Table Mapping

### Existing Tables

| Current table | Target treatment |
| --- | --- |
| `user` | Keep. Remove `full_name`; keep `email`, nullable `hashed_password`, `is_active`, `role`; add `preferred_language`. |
| `sellerprofile` | Keep concept. Add `first_name`, `last_name`; keep `business_category`, business, compliance, banking, and verification fields; replace embedded address columns with `business_address_id`. |
| `store` | Keep concept. Replace `seller_id` with `seller_profile_id`; replace embedded address columns with `address_id`. |
| `category` | Keep concept, but move display text into `category_translation`; add `service_id`, `slug`, and `sort_order`. |
| `masterproduct` | Keep concept, but move display text into `masterproduct_translation`; replace `category_id` with `subcategory_id`; keep compatibility `base_price`; add `slug` and keep `image_url`. |
| `storeinventory` | Keep mostly unchanged: `store_id`, `product_id`, `price`, `stock`, `is_available`, unique `(store_id, product_id)`. |
| `item` | Drop. It is scaffold residue and not part of product flows. |

### New Current-Flow Tables

| Table | Purpose |
| --- | --- |
| `language` | Supported languages. Initial seed: English, Hindi, Marathi, Gujarati, Punjabi. |
| `address` | Shared normalized address records for seller businesses, stores, customer saved addresses, and delivery addresses. |
| `customerprofile` | Customer role profile linked one-to-one to `user`. |
| `adminprofile` | Admin role profile linked one-to-one to `user`. |
| `customeraddress` | Customer saved address links, labels, and default selection. |
| `service` / `service_translation` | Top-level commerce verticals such as groceries, pharmacy, restaurant. |
| `subcategory` / `subcategory_translation` | Catalog level below category. |

### Future-Ready Tables

Create these now so schema work does not have to be repeated later, but keep endpoints/UI minimal until their feature specs are written:

- `cart`
- `cartitem`
- `order`
- `orderitem`
- `payment`
- `delivery`
- `review`
- `favorite`

## Model Design

Create focused SQLModel files rather than placing all models in one module:

- `models/base.py`: `BaseSchema`, `User`, `UserRole`, shared enum helpers if useful.
- `models/profile.py` or existing `models/seller.py` plus new profile modules: `CustomerProfile`, `AdminProfile`, `SellerProfile`, `VerificationStatus`.
- `models/address.py`: concrete `Address` table plus wire-format helpers. The current address mixin can be removed or retained only for request schemas.
- `models/catalog.py`: `Language`, `Service`, `ServiceTranslation`, `Category`, `CategoryTranslation`, `Subcategory`, `SubcategoryTranslation`, `MasterProduct`, `MasterProductTranslation`.
- `models/store.py`: `Store`, `StoreInventory`.
- `models/commerce.py`: carts, orders, payments, delivery, reviews, favorites, and their enums.

`models/__init__.py` and `migrations/env.py` must import every table model so Alembic autogenerate sees the full metadata.

## API Compatibility

The schema may be richer than the current UI. Existing API contracts should remain stable where practical:

- `/api/v1/auth/otp/verify` can still accept `full_name` for new customers. Internally, split it into `customerprofile.first_name` and `last_name` using a simple first-token/rest split.
- `/api/v1/auth/me` should continue returning enough user/profile display data for the frontend. If the frontend expects `full_name`, compose it from the role profile for now.
- `/api/v1/auth/seller/register` should keep the current request body shape, including `full_name`, `business_category`, and nested `address`. Internally:
  - Create `user`.
  - Create `address`.
  - Create `sellerprofile` with `first_name`, `last_name`, `business_address_id`, and existing seller fields.
  - Persist `business_category` on `sellerprofile` as a compatibility field used by admin review.
- Seller/admin review endpoints should continue returning nested `address` and display name fields.
- Store endpoints should continue returning `seller_id` if current frontend depends on it, but internally use `seller_profile_id`. If both are returned, document `seller_id` as compatibility output.
- Catalog list endpoints should return the current simple `Category` and `MasterProduct` shapes for the frontend, composed from English translations:
  - Category `name` and `description` come from `category_translation(language_code='en')`.
  - Product `name` and `description` come from `masterproduct_translation(language_code='en')`.
  - Product `base_price` comes from `masterproduct.base_price` until product admin UI is redesigned around inventory-specific pricing only.

## Migration Strategy

Use a reset baseline:

1. Create a new Alembic revision after the current head.
2. In `upgrade()`, drop obsolete existing tables and enum types with `checkfirst`/safe ordering where needed.
3. Recreate the complete target schema through Alembic operations generated from SQLModel metadata, with manual fixes for enums, constraints, partial indexes, and reserved table names.
4. In `downgrade()`, drop the new schema objects. It does not need to reconstruct the old schema because this is a destructive pre-production reset.
5. Update `scripts/reset_local_state.sh` so the normal local reset path rebuilds Docker volumes, runs Alembic to head, and seeds the new schema.

The migration docstring must clearly state that it is destructive and intended for local/pre-production environments.

## Seed Data

Update `backend/app/src/app/db/dev_seed.py` to seed a coherent small dataset:

- Languages: `en`, `hi`, `mr`, `gu`, `pa`.
- Users:
  - one admin
  - three active sellers
  - three seller applications for admin review
  - one customer
- Profiles for every seeded user, split by role.
- Addresses for seller businesses and stores.
- One service: groceries.
- Existing four categories as English translations under groceries.
- A simple subcategory structure that can hold the current 12 products.
- Current 12 products as `masterproduct` rows plus English translations.
- Existing 3 stores linked to seller profiles.
- Existing 26 inventory rows.

Do not seed future commerce rows unless tests or demos need them. Empty future-ready tables are acceptable.

## Error Handling And Constraints

- Use unique indexes for one-to-one profile relationships.
- Keep `ix_user_email` unique.
- Enforce unique slugs at the right scope:
  - service slug globally unique.
  - category slug unique per service.
  - subcategory slug unique per category.
  - product slug globally unique unless a scoped rule is intentionally chosen.
- Enforce unique translations per parent/language pair.
- Enforce unique inventory per store/product pair.
- Enforce unique cart per customer/store pair.
- Enforce unique cart item per cart/inventory pair.
- Enforce unique order item per order/inventory pair.
- Enforce favorite uniqueness per customer/product pair.
- Enforce review target exclusivity: exactly one of `product_id` or `store_id` must be non-null.
- Use explicit 404/409/422 responses in API code rather than relying on database integrity errors for normal user mistakes.

## Testing

Backend tests should cover:

- Alembic upgrade to head from an empty database.
- Canonical seed completes and expected counts match the new schema.
- OTP customer signup creates `user` plus `customerprofile`.
- Seller registration creates `user`, `address`, and `sellerprofile`.
- Admin seller review list still returns all expected fields.
- Store list/detail still returns nested addresses and inventory.
- Catalog list endpoints return composed English names/descriptions.
- Unique constraints return controlled API errors where current endpoints can trigger them.

Frontend verification should cover:

- Seller signup still submits successfully.
- Admin seller review page still displays applicants and address details.
- Store listing and store detail still render.
- Seller inventory management still creates and updates inventory.
- Admin catalog screens either keep working through compatibility responses or are explicitly scoped for follow-up redesign if translation-aware editing is too large for this change.

Quality gates:

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest -v`
- `npm run lint`
- `npm run build`

## Rollout

1. Merge the schema reset implementation before new feature work depends on current table shapes.
2. Run the local reset script to rebuild volumes and seed the new baseline.
3. Verify backend and frontend quality gates.
4. Keep `new_schema.sql` only as a temporary planning/reference artifact unless the team wants to maintain it as generated documentation.

## Risks

- The schema is significantly broader than the currently implemented app. The implementation must avoid wiring unfinished future tables into user-visible flows prematurely.
- Translation tables make catalog APIs more complex. Compatibility read models are needed so current frontend pages do not all change at once.
- Removing `User.full_name` affects auth and frontend display logic. Composed compatibility fields reduce blast radius.
- Changing `store.seller_id` to `seller_profile_id` affects seller authorization checks. API code must join through `SellerProfile.user_id`.
- Raw `new_schema.sql` has DDL issues and comments that describe missing indexes/checks. Running it directly would create an incomplete or invalid schema.

## Open Questions Resolved

- Existing data preservation: not required. Reset is acceptable.
- Migration style: destructive reset baseline.
- Future tables: create now, leave mostly unused until feature specs implement them.
