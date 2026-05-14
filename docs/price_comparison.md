<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Price Comparison on Checkout

The per-store checkout page (`/checkout/[storeId]/[serviceId]`) shows an opt-in panel that compares the customer's current sub-basket against up to two other serviceable stores offering the same service. The customer can one-click "switch" to an alternative store; the system atomically rebuilds the destination sub-basket (without touching the source cart) and navigates the customer to that store's checkout.

The feature is closed by default, so customers who don't want the cognitive load see a clean checkout page. It only becomes usable after the customer has picked a serviceable delivery address — without coordinates we can't filter candidate stores.

**Spec:** `docs/superpowers/specs/2026-05-14-checkout-price-comparison-design.md`
**Plan:** `docs/superpowers/plans/2026-05-14-checkout-price-comparison.md`

---

## User Flow

1. Customer reaches `/checkout/{A}/{svc}` with a non-empty `(A, svc)` sub-basket.
2. Customer picks a delivery address via `<AddressPicker>`. Serviceability against store A resolves through the existing PostGIS `ST_DWithin` check.
3. "Compare prices at nearby stores" toggle becomes enabled.
4. Customer clicks the toggle → frontend calls `GET /api/v1/carts/{A}/{svc}/compare?customer_address_id=<id>`.
5. Server returns 0, 1, or 2 alternatives, ranked by *effective total* ascending (tiebreak: distance).
6. UI renders a comparison table — columns are store A (current) + up to two alternatives; rows are the cart's items. Cells for items the alternative doesn't stock show "— Not stocked". Per-alternative footer breaks down `covered_subtotal` (items at that store's price) + `imputed_subtotal` (items that would stay at A's price) = `effective_total`.
7. Customer clicks "Shop at {Store B}".
8. Frontend opens `<SwitchStoreDialog>` listing what would be in the new B-cart, what isn't stocked at B, and any pre-existing B-cart that would be replaced. Confirms that the A-cart stays unchanged.
9. On confirm: `POST /api/v1/carts/{B}/{svc}/replace` with the items B stocks. Server validates, per-item caps to stock, drops items that became unavailable, and atomically wipes + repopulates the `(customer, B, svc)` cart row.
10. Frontend receives `{ cart, adjustments }`, stashes adjustments into `CartContext.lastReplaceAdjustments`, refreshes the cart context, and navigates to `/checkout/{B}/{svc}`.
11. The destination checkout page's `<ReplaceAdjustmentsBanner>` consumes the adjustments and renders a status banner if anything was capped, exhausted, or unavailable. The banner auto-clears when the customer navigates away.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Frontend: /checkout/{A}/{svc}                                       │
│                                                                      │
│  AddressPicker ──► pickerState.serviceable, selectedId               │
│                                                                      │
│  <PriceComparison ...>                                               │
│   [Compare prices ▼]   (disabled until address picker is serviceable)│
│    │                                                                 │
│    └─► GET /api/v1/carts/{A}/{svc}/compare?customer_address_id=…    │
│         (AbortController-cancellable)                                │
│         │                                                            │
│    ┌────▼───── alternatives ─────┐                                   │
│    │ <PriceComparisonTable>      │ ── "Shop at B" ─►                 │
│    └─────────────────────────────┘                                   │
│                                            │                         │
│                                            ▼                         │
│                                <SwitchStoreDialog>                   │
│                                    │ confirm                         │
│                                    ▼                                 │
│         POST /api/v1/carts/{B}/{svc}/replace                         │
│                                    │                                 │
│                                    ▼                                 │
│         CartContext.setReplaceAdjustments(adjustments)               │
│         router.push(`/checkout/{B}/{svc}`)                           │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Frontend: /checkout/{B}/{svc}                                       │
│                                                                      │
│  <ReplaceAdjustmentsBanner>  (mounted at top of page)                │
│      Reads CartContext.lastReplaceAdjustments                        │
│      Auto-clears on unmount                                          │
└─────────────────────────────────────────────────────────────────────┘
```

### Files

**Backend (FastAPI / SQLModel + PostGIS)**

| File | Responsibility |
|---|---|
| `backend/app/src/app/schemas/price_comparison.py` | Pydantic request/response models |
| `backend/app/src/app/services/price_comparison.py` | Pure `rank_candidates()` + session-bound `find_alternatives()` |
| `backend/app/src/app/api/carts.py` | `GET .../compare` + `POST .../replace` route handlers (appended to existing module) |

**Frontend (Next.js 16 / React 19 / CSS Modules)**

| File | Responsibility |
|---|---|
| `frontend/src/components/orders/PriceComparison.tsx` | Toggle, fetch lifecycle (AbortController), state machine, dialog wiring |
| `frontend/src/components/orders/PriceComparisonTable.tsx` | Presentational comparison table; flips to stacked cards `<768px` |
| `frontend/src/components/orders/SwitchStoreDialog.tsx` | Modal-wrapped confirmation dialog; uses existing `Modal.tsx` |
| `frontend/src/components/orders/ReplaceAdjustmentsBanner.tsx` | Post-switch banner consumed on the destination checkout page |
| `frontend/src/lib/priceComparison.ts` | Typed `fetchCompare` / `replaceSubBasket` wrappers |
| `frontend/src/lib/CartContext.tsx` | Extended with `lastReplaceAdjustments` state |
| `frontend/src/app/(customer)/[locale]/checkout/[storeId]/[serviceId]/page.tsx` | Mounts `<ReplaceAdjustmentsBanner>` + `<PriceComparison>` |
| `frontend/messages/{en,hi,mr,gu,pa}.json` | `Checkout.compare.*` i18n strings |
| `frontend/public/sw.js` | Skips `/api/v1/*` so per-customer responses are never cached |

### No schema changes

The feature reads `StoreInventory`, `MasterProduct(Translation)`, `SellerProfileService`, `CustomerAddress`, `Address` (with its PostGIS `geo` column), and writes `Cart` / `CartItem` rows that already exist. No new migrations.

---

## Ranking Algorithm

`services/price_comparison.py:find_alternatives` does the work:

1. **Candidate pool (PostGIS).** One raw-SQL query returns up to `CANDIDATE_POOL_LIMIT = 20` nearest **other** stores whose address is inside their own `delivery_radius_km` of the customer, **and** whose seller offers `service_id`. The query mirrors `api/stores.py:list_stores` (same `ST_DWithin` + `ST_Distance` pattern; same `sellerprofile_service` join). The source store is explicitly excluded.

   ```sql
   SELECT s.id, ST_Distance(a.geo, point) / 1000.0 AS distance_km
   FROM store s JOIN address a ON a.id = s.address_id
   WHERE s.is_active
     AND s.id <> :source_id
     AND a.geo IS NOT NULL
     AND ST_DWithin(a.geo, point, s.delivery_radius_km * 1000)
     AND EXISTS (
       SELECT 1 FROM sellerprofile_service sps
       WHERE sps.seller_profile_id = s.seller_profile_id
         AND sps.service_id = :service_id
     )
   ORDER BY ST_Distance(a.geo, point) ASC
   LIMIT :pool_limit
   ```

2. **Source-store prices.** Read `StoreInventory.price` for the cart's products at the source store. These are the *imputation prices* used for items the alternative doesn't stock.

3. **Candidate inventories.** One bulk query reads `StoreInventory` rows for every `(candidate_store, cart_product)` pair.

4. **Localized names.** `MasterProductTranslation` for the request's locale (`Accept-Language` header → `get_request_locale`), with English fallback for any product missing the requested locale.

5. **Build DTOs.** For each candidate store, compute per-cart-item:
   - If the candidate stocks the product **and** `is_available=true` **and** `stock > 0`:
     - `unit_price = inv.price`, `inventory_id = inv.id`, `imputed = false`, `stock = inv.stock`, `line_total = unit_price × quantity` (contributes to `covered_subtotal`, `covered_count`).
   - Otherwise:
     - `unit_price = source_store.price` (imputed at A's *current* live price), `inventory_id = null`, `is_available = false`, `stock = 0`, `imputed = true`, `line_total = unit_price × quantity` (contributes to `imputed_subtotal`, `missing_count`).

   `effective_total = covered_subtotal + imputed_subtotal`.

6. **Rank.** Delegate to the pure `rank_candidates(candidates)` helper:
   - Drop any candidate with `covered_count == 0` (zero-coverage stores are pure noise; same effective total as the source).
   - Sort by `(effective_total ASC, distance_km ASC)`.
   - Return the first `MAX_ALTERNATIVES = 2`.

### Why imputation?

Without imputation, a store that stocks one cheap item would beat a store that stocks nine. By charging missing items at the source store's price, we model "if you went to B for what they have and stayed at A for the rest, what's the combined cost?" — a fair apples-to-apples score that rewards both lower per-item prices and broader coverage.

The UI shows the breakdown explicitly:

```
At this store        ₹418.50 (4/5)
+ Stays at A         ₹80.00  (1/5)
═ Combined           ₹498.50    ← effective_total
```

Customers see exactly what they'd pay at each store, not a buried number.

---

## API Contract

### `GET /api/v1/carts/{store_id}/{service_id}/compare`

**Auth:** `Depends(get_current_customer)` (401 unauthenticated; 403 non-customer role).
**Query:** `customer_address_id: int` (required, refers to `CustomerAddress.id`).
**Locale:** `Accept-Language` header (`get_request_locale` dep).

**200 example:**

```jsonc
{
  "alternatives": [
    {
      "id": 17,
      "name": "More Supermarket",
      "distance_km": 2.1,
      "covered_count": 4,
      "missing_count": 1,
      "covered_subtotal": 418.50,
      "imputed_subtotal": 80.00,
      "effective_total": 498.50,
      "items": [
        {
          "product_id": 101,
          "product_name": "Aashirvaad Atta 5kg",
          "quantity": 1,
          "inventory_id": 33012,
          "unit_price": 268.00,
          "is_available": true,
          "stock": 4,
          "line_total": 268.00,
          "imputed": false
        },
        {
          "product_id": 117,
          "product_name": "Tata Salt 1kg",
          "quantity": 2,
          "inventory_id": null,
          "unit_price": 40.00,
          "is_available": false,
          "stock": 0,
          "line_total": 80.00,
          "imputed": true
        }
      ]
    }
  ]
}
```

`alternatives` may be empty, have 1, or have 2 entries. The frontend handles all three.

**Per-item invariant:** `unit_price` is always non-null and is the price used in `line_total`. `imputed: true` is the discriminator — when true, `inventory_id` is null, `is_available` is false, `stock` is 0, and `unit_price` reflects store A's current `StoreInventory.price` for that product. When false, all fields reflect the candidate store's live inventory row.

**Errors (frontend handling shown):**

| Code | `detail` | Trigger | Frontend |
|---|---|---|---|
| 400 | `invalid_address` | `customer_address_id` not owned, missing, or missing lat/lng | Hide panel, inline error |
| 404 | `cart_not_found` | No `(customer, store_id, service_id)` cart | Hide panel |
| 400 | `cart_empty` | Cart has 0 items (defensive — `delete_cart_item` removes empty carts) | Hide panel |
| 404 | `store_not_found` | Source store inactive or deleted | Hide panel, inline error |
| 409 | `service_unavailable` | Source seller no longer offers service | Hide panel, inline error |

Compare is a **passive fetch** — failures hide the panel and show an inline message; they do not redirect the customer off the checkout page. The existing order-placement handler at `page.tsx:144-149` catches the same failure modes when the customer tries to pay and redirects to `/cart` there.

### `POST /api/v1/carts/{store_id}/{service_id}/replace`

**Auth:** `Depends(get_current_customer)`.
**Body:**

```jsonc
{
  "items": [
    { "inventory_id": 33012, "quantity": 1 },
    { "inventory_id": 33019, "quantity": 3 }
  ]
}
```

`items` is bounded server-side: `min_length=1`, `max_length=200`. Items exceeding the cap return a 422 from FastAPI validation before any DB work.

**200 example:**

```jsonc
{
  "cart": { /* same shape as one entry in GET /carts: CartRead */ },
  "adjustments": [
    {
      "inventory_id": 33019,
      "requested_quantity": 5,
      "granted_quantity": 3,
      "reason": "stock_capped"
    }
  ]
}
```

**Per-item failure is graceful** (200 with adjustment, no error). This is a deliberate divergence from `add_cart_item` (which raises 409 on a single unavailable item) because `/replace` is a batch "switch store" action where dropping a single item with an adjustment beats torpedoing the whole intent on the first availability change.

Adjustment `reason` vocabulary (introduced by this feature):

| Reason | Trigger | Effect |
|---|---|---|
| `stock_capped` | `requested_quantity > current stock` | Item lands with `granted_quantity = stock` |
| `stock_exhausted` | `stock == 0` at write time | Item dropped entirely |
| `item_unavailable` | `is_available == false` at write time | Item dropped entirely |

**Behavior:**

1. Validate ownership: caller is the customer of `(customer, store_id, service_id)`.
2. `_validate_service_for_store` — destination service still offered by destination store + service is active.
3. For each submitted item: look up `StoreInventory`. Hard errors fire here:
   - Inventory not found → 404 `inventory_not_found`
   - Inventory belongs to a different store → 400 `inventory_store_mismatch`
   - Product resolves to a different service → 409 `service_mismatch` (inherited from `_assert_inventory_service_match`)
4. Per-item soft-drop / cap produces `adjustments`. Items that survive form the final write set.
5. If write set is empty → 400 `empty_items`.
6. Atomically inside a single transaction:
   - Get-or-create the `(customer, store_id, service_id)` cart row.
   - Delete all existing `CartItem` rows for that cart.
   - Insert the new items.
   - `commit()`.
7. The `(customer, source_store, service_id)` cart is never touched.
8. Return the new cart entry + adjustments.

**Hard errors:**

| Code | `detail` | Trigger |
|---|---|---|
| 400 | `empty_items` | Final write set empty after per-item filtering |
| 400 | `inventory_store_mismatch` | Inventory belongs to a different store (bug — UI never produces this) |
| 409 | `service_mismatch` | Inventory's product resolves to a different service (bug) |
| 409 | `service_unavailable` | Destination store no longer offers `service_id` |
| 404 | `inventory_not_found` | Inventory deleted between compare and replace |

The frontend redirects to `/cart` on `service_unavailable` or `service_mismatch` because those mean the destination store can no longer serve this cart — the customer needs to go back to the cart page and figure out what to do.

---

## Frontend State Machine

```
disabled  ◄── pickerLoading || !serviceable || customerAddressId === null
   │
   ▼  click toggle
loading   (fetch /compare via AbortController)
   │
   ├── error  ──► <Retry>  (re-fires the fetch)
   ├── empty  ──► "No other stores in your area offer this service right now."
   └── loaded ──► <PriceComparisonTable>
                    │
                    ▼  click "Shop at B"
                 <SwitchStoreDialog>  (chosen = altB)
                    │
                    ├── cancel ──► back to loaded
                    └── confirm
                          │
                          ▼  POST /replace
                       switching  (submitting = true; Shop-at buttons + dialog
                                   Cancel/X/Escape all disabled or guarded)
                          │
                          ├── error ──► dialog stays open with inline error
                          ├── service_unavailable / service_mismatch ──►
                          │       clearReplaceAdjustments() + router.push("/cart")
                          └── ok ──► setReplaceAdjustments(res.adjustments)
                                     refresh()
                                     router.push("/checkout/{B}/{svc}")
```

Key behaviors:

- **AbortController** cancels any in-flight `/compare` request when the toggle is closed or the component unmounts.
- **`customerAddressId`** is sourced from `pickerState.selectedId` (canonical) rather than a separately-tracked `addressId` — matches the place-order button's gate.
- **Shop-at buttons** are disabled when `chosen !== null || submitting` so a customer can't open the dialog for one alternative while another switch is in flight.
- **`SwitchStoreDialog`** routes Escape, backdrop click, ✕, and Cancel all through the same `submitting`-guarded close path — none of them can unmount the dialog mid-network-call.
- **`<ReplaceAdjustmentsBanner>`** clears its context state on unmount, so the banner doesn't follow the customer to other pages (including back to the source store's checkout).
- **`CartContext`** also clears `lastReplaceAdjustments` when `dbUser` becomes null, so a logout doesn't leak prior-user adjustments to the next customer on the same device.

---

## Edge Cases and Race Conditions

| Scenario | Outcome |
|---|---|
| Customer opens compare → seller raises B's price → customer confirms switch | `/replace` succeeds at the current (raised) B price. B's checkout page shows the new price via `refresh()`. Price drift is not surfaced as a banner — only stock/availability changes are. |
| Seller disables an item on B between compare and switch | `/replace` drops the item with `adjustment.reason = "item_unavailable"`. If at least one item still lands → 200 + banner. If all drop → 400 `empty_items`, dialog stays open. |
| Seller deletes a master product between compare and switch | `/replace` returns 404 `inventory_not_found`. Dialog surfaces the error; customer can re-toggle to refresh. |
| Customer's A-cart changes in another tab | `/replace` operates on the items array the frontend sends (subset of what compare returned). A-cart is never touched. Stale missing-items list in the dialog is acceptable. |
| Customer double-clicks "Create cart" | Frontend disables the button while `submitting = true`. Backend `/replace` is naturally idempotent inside its transaction (wipe + insert). |
| Customer's address has no `geo` (lat/lng null) | 400 `invalid_address`. Inline error; user re-picks. |
| Toggle closed mid-fetch then reopened | `AbortController` cancels the in-flight request. Re-open triggers a new fetch. |
| User signs out, second customer signs in on same device | `CartContext` clears `lastReplaceAdjustments` on `dbUser` going null; service worker does **not** cache `/api/v1/*` paths; the new customer sees a clean checkout. |
| Customer paid both A and B (kept both sub-baskets and checked out separately) | By design — sub-basket parallelism is supported by the unique-key `(customer, store, service)`. The dialog copy clarifies "Your {A} cart is not changed". |
| Serviceability of B changes between compare and order placement at B | Order-placement re-asserts `ST_DWithin` (per existing checkout flow). Cart-write does not re-check serviceability — matches existing semantics. |

---

## Security & Authorization

- Both endpoints are gated by `get_current_customer` — 401 unauth, 403 for seller/admin roles.
- `customer_address_id` ownership is verified via a JOIN through `CustomerAddress.customer_profile_id`; cross-tenant address lookup returns the same `invalid_address` 400 as "not found" so existence isn't enumerable.
- Tenant isolation on `/replace` is structural: the cart row is resolved by `_get_or_create_cart(profile_id, …)` where `profile_id` is derived from the JWT subject. A customer cannot write into another customer's cart.
- PostGIS SQL uses `text(...).bindparams(...)` exclusively — no string interpolation of user input. The only `f"..."` interpolation is a hardcoded SRID expression.
- `ReplaceRequest.items` is capped at 200 entries to prevent cost-amplification DoS (each item triggers two DB lookups inside the transaction).
- `frontend/public/sw.js` explicitly skips any URL whose pathname starts with `/api/`. Per-customer responses never enter the shared `khanabazaar-v1` cache, even on shared devices.
- **Known acceptable trade-off:** `/replace` distinguishes `404 inventory_not_found` from `400 inventory_store_mismatch`, which lets an authenticated customer probe whether an `inventory_id` exists globally. Stock and price are already public via the storefront API, so the marginal leak is "this id is real" — accepted per existing convention.
- **MVP-scope deferral:** no per-customer rate limit on `/compare`. The endpoint surfaces competitor prices, distances, and stock counts — defensible at MVP because the storefront API already exposes per-store inventory; worth adding a hard per-minute throttle if abuse signals appear.

---

## Internationalization

All UI strings live under `Checkout.compare.*` in `frontend/messages/{en,hi,mr,gu,pa}.json`. The native locales currently use English placeholder values (matches the project's existing fallback practice); native translations are a follow-up.

Product and store names returned by `/compare` are localized server-side via `MasterProductTranslation` for the request's `Accept-Language` header (`get_request_locale` dep). If a translation is missing in the requested locale, the response falls back to English.

Plural forms use ICU MessageFormat (`{count, plural, one {…} other {…}}`) for the banner adjustment summaries.

---

## Testing

### Backend (real Postgres `khanabazaar_test`)

| File | Coverage |
|---|---|
| `tests/test_price_comparison_ranking.py` | 6 unit tests for the pure `rank_candidates` helper: zero-coverage drop, sort order, tiebreak by distance, max-2 cap, empty, single passthrough. |
| `tests/test_carts_compare.py` | 6 integration tests: happy-path with 4 candidate stores (one out of range, one wrong service); effective-total math; imputed flag on missing items; `invalid_address`; `cart_not_found`; unauth. |
| `tests/test_carts_replace.py` | 11 integration tests: happy path; pre-existing B-cart wiped; `stock_capped` adjustment; `stock_exhausted` adjustment; `item_unavailable` adjustment; `empty_items` when all drop; `inventory_store_mismatch`; `inventory_not_found`; source A-cart preservation; idempotent retry; unauth. |

Pytest uses the project's standard fixtures (drop+recreate schema per function, real PostGIS, eager Celery, dependency-overridden auth). The seed fixture for `/compare` builds 4 stores at distinct lat/lng with overlapping inventory in real Mumbai coordinates inside a 5 km delivery radius.

### Frontend

The project has no frontend test framework configured. Verification is done via:
- `npx tsc --noEmit` (typecheck)
- `npm run lint` (ESLint — new files are clean; two pre-existing errors in unrelated files remain)
- Manual QA matrix (see spec §5.3) executed against `scripts/dev.sh start`

---

## Performance & Observability

- Candidate pool is bounded to 20 nearest stores via SQL `LIMIT`. Inventory fan-out is `len(candidates) × len(cart product_ids)` — well-bounded for MVP cart sizes.
- Compare is a single round-trip per toggle expansion. The frontend does not poll.
- `/replace` writes are O(n) in the number of items submitted; the transaction wraps the delete + inserts as a single commit.
- No new caching layer.
- The endpoints log at FastAPI's default level — no custom logging infra was added.

---

## Known Limitations / Future Work

| Item | Why deferred |
|---|---|
| Address handoff to destination checkout (`?customer_address_id=…` query param) | UX papercut: the customer re-picks the address on the destination page. Not a blocker. |
| Rate limit on `/compare` | Spec-acknowledged; price-scrape vector. Add when abuse signals appear. |
| Telemetry / analytics | The codebase has no analytics infra. |
| Native i18n for `Checkout.compare.*` in hi/mr/gu/pa | English placeholders work; native translations are a content task. |
| Cleanup of pre-existing free-text error strings in `carts.py` | Not introduced by this feature. |
| Per-trip user-set `radius_km` on `/compare` (analogous to `list_stores`) | Not requested. The endpoint trusts each candidate store's own `delivery_radius_km`. |
| `services/addresses.py` extraction | `_resolve_address` still lives in `services/checkout.py`. The compare handler inlines an equivalent check; refactor is structural, no behavioral change. |

---

## Related Documents

- `docs/architecture.md` — overall system topology
- `docs/flows.md` — guest-cart, auth, per-store-checkout flows
- `docs/superpowers/specs/2026-05-14-checkout-price-comparison-design.md` — full design spec
- `docs/superpowers/plans/2026-05-14-checkout-price-comparison.md` — implementation plan with task-by-task code
