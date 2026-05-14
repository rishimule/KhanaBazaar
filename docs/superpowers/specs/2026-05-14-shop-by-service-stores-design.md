# Shop-by-Service: Per-Service Stores Listing + Service Deep-Link

**Date:** 2026-05-14
**Status:** Approved (design)

## Problem

The home page renders a "Shop by service" grid built from `/api/v1/catalog/services`, but every tile links to `/stores`, ignoring the chosen service. There is no way to browse "stores that offer Grocery" or "stores that offer Pharmacy". When a user then opens a store, they land on the first service tab regardless of what they came from.

We want:

1. Tapping a service tile takes the user to a list of stores that offer that service, sorted by distance when a delivery location is known.
2. Tapping a store on that list opens the store detail page with that service already selected.

## Non-goals

- No new "open now" / hours model.
- No stock-aware filtering on the list (a store that offers a service but currently has zero inventory still appears — see Open Issues).
- No new entity. We reuse `SellerProfileService` (junction) and the existing `Service` row.

## User flow

1. Home page → "Shop by service" → click "Grocery" tile.
2. Land on `/stores?service=grocery`. Header reads **"Showing Grocery stores · Clear"**. Cards show distance when a delivery location is set; empty state when none match.
3. Click a store card → `/stores/<id>?service=<service_id>`. Store detail page mounts with the Grocery service tab pre-selected, category sidebar pointing at the first Grocery category.
4. Back button returns to the filtered list. Forward / direct visits to `/stores/<id>` (no query param) behave as today.

## Architecture

### Routes

| URL | Page |
|-----|------|
| `/<locale>/stores?service=<slug>` | Existing stores list, filtered. Slug param is optional; absent = current behavior. |
| `/<locale>/stores/<id>?service=<service_id>` | Existing store detail. `service` query param seeds initial service tab, then is dropped via `router.replace`. |

Slug is used in the list URL (readable, locale-neutral). Numeric id is used in the deep link because the store detail page's state is keyed by service id and the storefront response also uses ids.

### Backend

`GET /api/v1/stores/` gains an optional `service: str` query parameter.

Behavior:

1. Resolve `service` slug → `Service` row filtered by `is_active = true`. Unknown / inactive slug → `400` with `detail="unknown_service"`. Empty result is reserved for "no stores match"; an unknown slug is a programming error and must fail loud.
2. Apply a filter that restricts the result to stores whose `seller_profile_id` has a `SellerProfileService` row with `service_id = <resolved id>`. The junction table name is `sellerprofile_service`; the SQLModel class is `SellerProfileService`. The filter must apply in both branches of the handler:
   - No-location branch: add `.where(Store.seller_profile_id.in_(select(SellerProfileService.seller_profile_id).where(SellerProfileService.service_id == sid)))` to the ORM statement.
   - Lat/lng raw-SQL branch: add an `EXISTS (SELECT 1 FROM sellerprofile_service sps WHERE sps.seller_profile_id = s.seller_profile_id AND sps.service_id = :service_id)` clause; bind `:service_id`.
3. Sort is unchanged: `ST_Distance` ASC when `lat`+`lng`+`sort=distance`; otherwise `s.id ASC`.
4. Pagination (`skip`, `limit`) and the existing `radius_km` clamp continue to work alongside the filter.

No response shape change. Each `StoreRead` already carries `services` (resolved via `list_profile_services`), which the frontend uses to map the slug back to a service id for deep-linking.

#### Tests (backend)

Add to `backend/app/tests/test_stores.py`:

- `test_list_stores_filter_by_service` — seed two stores; seller A offers Grocery, seller B offers Pharmacy. `GET /stores/?service=grocery` returns only A. `?service=pharmacy` returns only B.
- `test_list_stores_filter_unknown_service` — `?service=does-not-exist` → 400.
- `test_list_stores_filter_inactive_service` — flip `Service.is_active=false`, `?service=<slug>` → 400.
- `test_list_stores_filter_with_distance_sort` — two Grocery sellers at different distances; `?service=grocery&lat=&lng=&sort=distance` returns both, ordered by distance, with `distance_km` populated.
- `test_list_stores_filter_includes_stockless_offering` — seller has Grocery in `SellerProfileService` but zero `StoreInventory` rows. `?service=grocery` still returns the store. Locks in the non-goal that the list is offer-based, not stock-based.

### Frontend

#### Home page (`frontend/src/app/(customer)/[locale]/page.tsx`)

Change the "Shop by service" tile `href` from `/stores` to `` `/stores?service=${s.slug}` ``. No other changes; the existing grid, glyph, and label logic stays.

#### Stores list page (`frontend/src/app/(customer)/[locale]/stores/page.tsx`)

- Read `useSearchParams().get("service")` (slug, may be null).
- Add a one-time fetch of `/api/v1/catalog/services` (mirror the home page pattern) so the page can resolve slug → localized service name for the header chip. Cache via module-level memo or `useMemo`; data is small.
- Build fetch URL with `service` appended when present: `` `/api/v1/stores/?service=${slug}` `` (plus the existing lat/lng/sort segment when a delivery location is set).
- Refetch on slug change.
- Header: when a service is selected, render a chip reading "Showing &lt;Service name&gt; stores" with a "Clear" link to `/stores`. When no slug, keep the current title.
- Card href: when a service is selected and the store's `services` array contains a matching `slug`, link to `` `/stores/${store.id}?service=${matched.id}` ``. Otherwise (slug not found on store, which would be a backend mismatch) fall back to `/stores/${store.id}`.
- Empty state:
  - Slug + no location + 0 stores → "No stores offer &lt;Service&gt; yet. Try setting a delivery location."
  - Slug + location + 0 stores → "No stores deliver &lt;Service&gt; to your selected location yet."
  - No slug → existing copy.
- **Suspense / dynamic rendering:** `useSearchParams` in a client component opts the page out of fully static rendering. Wrap the body in `<Suspense>` and provide a fallback matching the existing loading state. (Equivalent escape hatch: `export const dynamic = "force-dynamic"`. Prefer Suspense — keeps the static shell.)

#### Store detail page (`frontend/src/app/(customer)/[locale]/stores/[id]/page.tsx`)

Add deep-link seeding:

1. Read `useSearchParams().get("service")` once via a ref-guarded effect so the seed runs at most once per mount.
2. Effect fires when `storefront !== null`. Parse the query value as an integer. If valid and the id appears in `storefront.services`, set `activeServiceId` and `activeCategoryId = matched.categories[0]?.id ?? null`.
3. If the id is valid but the service is not in `storefront.services` (meaning the seller offers it but has no stock), check `store.services` (full offered set). If present there, still set `activeServiceId` to that id and render the existing empty branch — the `services.length === 0` branch already shows "noProductsYet"; we'll mirror it per-service. Add a "noProductsForService" copy and render it instead of the categories block when `activeServiceNode` is null but `requestedServiceId` is in `store.services`.
4. After seeding, call `router.replace(\`/stores/\${id}\`, { scroll: false })` so the param doesn't re-trigger on re-render or appear in shared URLs. (Imports `useRouter` from `next/navigation`.)
5. Invalid / missing param: existing behavior (fallback to first service) — no change.

The existing `activeServiceNode = services.find(...) ?? services[0]` line means we also need a separate piece of state (or an effect) to track *which* service id was requested but absent from the storefront, so the empty-per-service branch can render. Simplest approach: a `requestedMissingServiceId: number | null` state, set in the seeding effect when the requested id is in `store.services` but not in `storefront.services`. The render gate becomes:

```
if (services.length === 0 && !requestedMissingServiceId) -> "noProductsYet" (existing)
else if (requestedMissingServiceId !== null && !activeServiceNode) -> "noProductsForService"
else -> render service tabs + categories
```

When the seller adds stock later, the storefront fetch on next visit will surface that service in `storefront.services` and the empty branch will not trigger.

## Translations

Add keys to the existing locale files (mirror present `Stores` / `StoreDetail` namespaces):

- `Stores.filteredHeader` — "Showing {service} stores" (positional ICU)
- `Stores.clearFilter` — "Clear"
- `Stores.emptyNoLocation` — "No stores offer {service} yet. Try setting a delivery location."
- `Stores.emptyWithLocation` — "No stores deliver {service} to your selected location yet."
- `StoreDetail.noProductsForService` — "No {service} products yet at this store."

## Data flow

```
Home tile (slug)
   |
   v
/stores?service=<slug>  --GET /api/v1/stores/?service=<slug>[&lat=&lng=&sort=distance]
   |
   |   each card: href = /stores/<id>?service=<service_id>
   v
/stores/<id>?service=<service_id>  --GET /api/v1/stores/<id>/storefront
   | effect: seed activeServiceId, router.replace
   v
/stores/<id>  (param dropped, state retained)
```

## Edge cases

- **Unknown / inactive slug**: backend 400; frontend treats it as a hard error (`ApiError` already surfaces a toast / inline message in the existing fetch wrapper).
- **Slug present, no location**: list returns all matching stores ordered by id; empty state nudges toward setting a delivery location.
- **Slug present, has location, no stores in radius**: empty state per copy above.
- **Store offers service but zero stock for it** (deep-link target missing from storefront): show per-service empty state inside the store page rather than silently switching tabs.
- **Stale cache on store detail**: the seeding effect must wait for `storefront !== null`. The page already renders cached storefront synchronously when available; the effect runs against whichever payload is loaded (cached or fresh) and the storefront services list is identical for both within a session.
- **Locale switch on the listing page**: service display name comes from the localized `/api/v1/catalog/services` payload; switching locales triggers re-fetch.
- **Repeat clicks**: `router.replace` is idempotent; the ref guards re-runs.
- **Storefront cache TTL**: per-service empty state can linger briefly after the seller adds stock for a previously-empty service, until `storefrontCache` revalidates. This is existing cache behavior, not introduced by this change.

## Open issues

- We deliberately do **not** filter the list by stock. A seller listed under "Grocery" can have zero Grocery inventory and still appear. The store page handles this with an empty-for-service state. If this proves noisy in practice we can introduce a stock-aware variant (`/stores/?service=<slug>&has_stock=true`) without breaking the URL contract.
- No "open now" model. Out of scope until store hours are added to the schema.

## Files touched (estimated)

Backend:

- `backend/app/src/app/api/stores.py` — extend `list_stores` (one handler, both branches).
- `backend/app/tests/test_stores.py` — four new tests.

Frontend:

- `frontend/src/app/(customer)/[locale]/page.tsx` — tile href.
- `frontend/src/app/(customer)/[locale]/stores/page.tsx` — slug filter, header chip, empty states, Suspense wrap.
- `frontend/src/app/(customer)/[locale]/stores/[id]/page.tsx` — deep-link seeding, per-service empty state, `router.replace`.
- `frontend/messages/<locale>.json` — new translation keys for each locale present.
- `frontend/src/app/(customer)/[locale]/stores/page.module.css` — chip + Clear-link styles (small additions).

No new dependencies. No schema or migration changes.
