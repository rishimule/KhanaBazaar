# Store detail page: storefront aggregation + smooth load

**Date:** 2026-05-11
**Status:** Approved (autonomous execution)
**Owner:** Rishi

## Problem

`/stores/[id]` fires six parallel requests on mount: store, inventory, the
full master-product catalog (1500 rows post-seed expansion), services,
categories, and subcategories. The page then joins all six client-side
into a service → category → subcategory → product tree.

Two costs:

1. **Payload waste.** Average store stocks ~40 SKUs but the page
   downloads the entire 1500-product catalog (and 100 categories,
   300 subcategories, 12 services) to label them.
2. **First-paint latency.** `/catalog/products` runs an N+1 translation
   lookup per row — ~3000 sub-queries for 1500 products. The skeleton
   sits on screen until the slowest of the six round trips returns.

Adding more sellers makes this worse: more candidate products,
more translations, more bytes per render.

## Goal

- Cut the store-detail wire payload to what the store actually stocks.
- Replace the six-fetch fan-out with one round trip whose response
  matches the page's render shape.
- Keep the existing UX (sidebar, scroll-spy, cart rail) and stay on the
  current "use client" component — no RSC rewrite.

## Non-goals

- No service worker / no SWR / no react-query install.
- No virtual scrolling — typical store renders < 100 cards.
- No RSC migration; the page stays client-rendered.
- No pagination of the storefront response. Defer until stores
  routinely exceed ~500 SKUs.
- Admin / seller dashboards keep using `/catalog/products` +
  `/stores/{id}/inventory` as today — they need the full catalog.

## Design

### New endpoint: `GET /api/v1/stores/{store_id}/storefront`

Public read endpoint (matches the existing public `/stores/{id}` +
`/stores/{id}/inventory` pair). Returns a single payload shaped like the
render tree the page already builds.

**Response shape:**

```json
{
  "store": {
    "id": 22,
    "name": "Quick Greenery #22",
    "address": { "...": "..." },
    "delivery_radius_km": 5,
    "pin_confirmed": true,
    "is_open": true
  },
  "services": [
    {
      "id": 11,
      "slug": "flowers-plants",
      "name": "Flowers & Plants",
      "sort_order": 10,
      "categories": [
        {
          "id": 92,
          "slug": "bouquets",
          "name": "Bouquets",
          "subcategories": [
            {
              "id": 274,
              "slug": "rose-bouquets",
              "name": "Rose Bouquets",
              "items": [
                {
                  "inventory_id": 715,
                  "product_id": 1412,
                  "product_name": "FNP Red Rose Bouquet (6 Stems)",
                  "image_url": "/images/products/...",
                  "description": "...",
                  "price": 567.6,
                  "stock": 41
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

Empty store ⇒ `services: []`. Inactive / missing store ⇒ 404.

### Backend implementation

`app/api/stores.py::list_store_storefront`:

1. Validate store exists and is active (mirrors `list_store_inventory`).
2. Run one `select` joining:
   `StoreInventory` → `MasterProduct` → `Subcategory` → `Category` → `Service`,
   filtered by `store_id` and `is_available`.
3. Pull all four translation tables in a second `select ... where id in (...)`
   call per table, keyed by language with English fallback. Four extra
   round trips total, not N per row.
4. Group the rows in Python into the response tree, sorted by:
   `Service.sort_order`, `Category.sort_order`, `Subcategory.sort_order`,
   then product name.
5. Return the response.

No DB writes. No auth. Stays inside the existing public-route group.

Schemas live in `app/schemas/storefront.py`:

- `StorefrontItem` (inventory_id, product_id, product_name, image_url,
  description, price, stock).
- `StorefrontSubcategory` (id, slug, name, items[]).
- `StorefrontCategory` (id, slug, name, subcategories[]).
- `StorefrontService` (id, slug, name, sort_order, categories[]).
- `StorefrontResponse` (store: existing `StoreRead`, services[]).

### Frontend integration

`frontend/src/app/(customer)/[locale]/stores/[id]/page.tsx`:

1. Replace the six-fetch `Promise.all` with one call to
   `get<StorefrontResponse>(\`/api/v1/stores/${id}/storefront\`)`.
2. Delete `buildTree` and the four catalog state slices
   (`services`, `categories`, `subcategories`, `inventory`).
3. Keep the existing sidebar, scroll-spy, cart rail, and skeleton state
   unchanged — they just receive the tree from the response now.

### Client-side cache

Module-level `Map<number, { data, expiresAt }>` in a new
`frontend/src/lib/storefrontCache.ts`. 60-second TTL.

- Cache hit + not expired ⇒ return cached data immediately, skip the
  fetch entirely. Page paints synchronously on revisit.
- Cache hit + expired ⇒ render cached data, kick off a background
  revalidate, swap in fresh data when it lands.
- Cache miss ⇒ fetch, show skeleton.

Tiny in scope, no dependency. Survives only within a session — clears on
hard refresh. Good enough for the "smooth on back/forward" win.

### Out-of-stock items

Endpoint filters on `is_available` (mirrors current
`list_store_inventory`). Out-of-stock rows are dropped server-side.
Future: could keep them and let the UI gray them out.

### Localization

Endpoint accepts the standard `lang` request locale (same dependency
used by catalog routes). Translation lookups fall back to English when a
language has no row, same pattern as the catalog endpoints.

## Performance expectations

For a typical 40-SKU store, request count from the page drops 6 → 1,
JSON payload drops from ~250 KB (mostly the 1500-product catalog) to
~10 KB (the store's actual stock). Backend translation queries drop
from ~3000 (`/catalog/products` N+1) to 4 per request.

## Testing

`backend/app/tests/test_storefront_endpoint.py` covers:

- happy path: a store stocking products across two services renders a
  well-formed tree with correct counts and sort order.
- empty store (no inventory): `services` is `[]`, 200 OK.
- non-existent store id ⇒ 404.
- inactive store ⇒ 404.
- out-of-stock inventory (`is_available=false`) is excluded.
- `lang=hi` with missing Hindi translation falls back to English.

No frontend tests (project convention).

## Migration / rollout

Additive. Old endpoints stay. Admin and seller dashboards keep working.
Frontend store detail page swaps over in the same PR. Other pages
(home, store list) keep their existing data flow.

## Risks

- Group-by-tree logic in Python is the only nontrivial new code. Unit
  test covers the sort order and grouping.
- Translation fallback pattern is copied verbatim from `catalog.py` to
  keep behavior consistent.
- Cache TTL is 60s. If a seller updates inventory while a customer is
  on the page, the customer sees stale prices for up to 60s. Acceptable
  for browsing; checkout already revalidates inventory transactionally.

## Open questions

None — moving to implementation.
