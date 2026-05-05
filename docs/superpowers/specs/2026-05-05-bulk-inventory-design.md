# Bulk Inventory Editor — Design Spec

**Date**: 2026-05-05
**Status**: Awaiting user review

## 1. Goal

Let approved sellers add or edit dozens of inventory rows in one screen instead of one modal at a time. Enforce that sellers may only stock products belonging to their admin-approved services (Grocery, Electronics, Pharmacy, …).

The current flow (`/seller/inventory`) requires a modal-per-product. A seller onboarding 50 SKUs must repeat 50 dialogs and has no service-membership constraint — they can add any master product in the catalog.

## 2. Decisions (locked)

| # | Decision | Rationale |
|---|---|---|
| Q1 | Spreadsheet editor (in-app table). Defer CSV upload. | Covers stated 50-row case without a parsing pipeline. Mobile fallback stays usable. YAGNI on CSV until 200+-row sellers appear. |
| Q2 | Filtered checklist + drill-down filters in product picker | Sellers think in service → category → subcategory; search covers edge cases. Already-stocked products hidden. |
| Q3 | Bulk view supports ADD (new rows) AND EDIT (existing rows). Bulk delete deferred. | Seasonal price/stock updates are a real recurring need. Delete is rarer; existing single-row delete remains. |
| Q4 | Bulk-fill toolbar (`set price = X`, `set stock = Y`, `+/-N%`) plus default-to-base-price on blank | Saves typing across ~50 similar SKUs. Per-row override always allowed. |
| Q5 | Frontend pre-validates; server runs all-or-nothing transaction (defensive) | Fast feedback on invalid rows; DB never half-applied. |
| Q6 | Single upsert endpoint: `PUT /api/v1/stores/{store_id}/inventory/bulk`. Server detects insert vs update by `(store_id, product_id)` lookup. | Sheet rows are mixed new+existing; one round-trip; atomic. |
| Q7 | Service-membership constraint enforced everywhere via shared validator. Existing `POST /inventory` retrofitted. | Constraint is a security/business invariant. Single source of truth. |
| Q8 | New endpoint `GET /api/v1/sellers/me/eligible-products` returns server-joined product list filtered by seller's approved services. | Server already knows seller services from JWT. One round-trip. Less client coupling. |
| Q9 | Bulk request capped at **200 rows** per request | Bounds transaction time. Frontend chunks if user really exceeds. |
| Q10 | New sub-route `/seller/inventory/bulk`. Existing `/seller/inventory` keeps single-row UX. | Clean separation; bulk view is a power tool. Single-row stays mobile-friendly. |
| Q11 | Mobile shows banner: "Bulk editor works best on desktop." Functional but not optimized. | Spreadsheet UX collapses below ~768px. Single-row remains mobile path. |
| Q12 | Lock existing inventory rows in id order via `lock_inventory_rows()` during upsert | Avoids deadlocks with concurrent checkout — same lock pattern already in `services/checkout.py`. |

## 3. Data model

**No schema changes.** Existing tables suffice:

- `storeinventory` (`store_id`, `product_id` already unique together via service layer)
- `sellerprofile_service` (junction — already populated at signup/admin approval)
- `masterproduct` → `subcategory` → `category` → `service` (existing chain)

## 4. Backend

### 4.1 New service helpers — `services/inventory.py`

```python
async def assert_products_in_seller_services(
    session: AsyncSession,
    seller_profile_id: int,
    product_ids: Iterable[int],
) -> None:
    """Raise HTTPException(403) if any product's service is not in the
    seller's approved SellerProfileService set. Single SELECT joining
    masterproduct → subcategory → category and intersecting with
    sellerprofile_service.service_id."""
```

```python
async def bulk_upsert_inventory(
    session: AsyncSession,
    store_id: int,
    items: list[BulkInventoryItem],
) -> list[StoreInventory]:
    """Single-transaction upsert.

    1. Dedup by product_id (last write wins per product).
    2. SELECT existing rows WHERE (store_id, product_id) IN payload.
    3. lock_inventory_rows(existing_ids) — deterministic id order.
    4. UPDATE locked rows in place; INSERT missing rows.
    5. Caller commits. Service raises on any validation failure
       so the surrounding transaction rolls back atomically.
    """
```

### 4.2 New endpoint — `api/sellers.py`

```python
GET /api/v1/sellers/me/eligible-products
```

Auth: `get_current_seller`.
Returns: list of `EligibleProduct` (joined master-product + category + subcategory + service names + already-in-inventory flag for the seller's store). Filtered to products whose owning service is in `SellerProfileService` for the caller's profile.

**Localization:** the `*_name` fields are pulled from the corresponding translation tables (`MasterProductTranslation`, `SubcategoryTranslation`, `CategoryTranslation`, `ServiceTranslation`) using `lang: str = Depends(get_request_locale)` with an English fallback when a translation is missing — same pattern as `GET /catalog/products`.

**Store resolution:** the `in_inventory` flag is computed against the caller's single store (looked up via `SellerProfile.id` → `Store.seller_profile_id`). If the seller has no store yet (admin not yet approved them), endpoint returns 409 `STORE_NOT_PROVISIONED` — matches the existing dashboard guard.

Response shape:

```json
[{
  "id": 42,
  "name": "Aashirvaad Atta 5kg",
  "base_price": 280.0,
  "subcategory_id": 7,
  "subcategory_name": "Atta & Flour",
  "category_id": 3,
  "category_name": "Staples",
  "service_id": 1,
  "service_name": "Grocery",
  "in_inventory": false
}]
```

For v1, returns full result set (catalog is small). Pagination params `?limit=&offset=&q=` reserved for future without breaking change.

### 4.3 New endpoint — `api/stores.py`

```python
PUT /api/v1/stores/{store_id}/inventory/bulk
Body: { "items": [{ "product_id": int, "price": float, "stock": int, "is_available": bool }, ...] }
```

Auth: `get_current_seller` + `_authorize_store_ownership`.
Validations (all must pass before any write):

1. `len(items) <= 200`.
2. Each item: `price > 0`, `price <= 999_999`, `stock >= 0`, `is_available: bool`.
3. Distinct product_ids exist in `masterproduct`.
4. `assert_products_in_seller_services(...)` — covers the user-stated constraint.

On success: returns the upserted `StoreInventory` rows. Single transaction; on any error returns 4xx with structured per-row errors:

```json
{
  "detail": "Validation failed",
  "errors": [
    { "index": 17, "product_id": 42, "code": "PRICE_INVALID", "message": "Price must be > 0" },
    { "index": 23, "product_id": 88, "code": "SERVICE_NOT_APPROVED", "message": "Pharmacy not in your approved services" }
  ]
}
```

### 4.4 Retrofit existing single-row `POST /inventory`

Add `assert_products_in_seller_services(session, profile.id, [inventory.product_id])` before insert. Returns 403 with `SERVICE_NOT_APPROVED` if violated. **Behavior change** documented in `docs/flows.md`.

### 4.5 New schemas — `schemas/inventory.py` (new file)

```python
# Note: BulkInventoryItem has NO `inventory_id`. Server resolves
# insert-vs-update purely by (store_id, product_id) lookup. The
# frontend tracks its own `inventory_id` for UI/dirty-state only.
class BulkInventoryItem(BaseModel):
    product_id: int
    price: float
    stock: int
    is_available: bool = True

class BulkInventoryRequest(BaseModel):
    items: list[BulkInventoryItem]

class BulkInventoryError(BaseModel):
    index: int
    product_id: int
    code: Literal["PRICE_INVALID", "STOCK_INVALID", "PRODUCT_NOT_FOUND",
                  "SERVICE_NOT_APPROVED", "DUPLICATE_PRODUCT", "ROW_LIMIT"]
    message: str

class EligibleProduct(BaseModel):
    id: int
    name: str
    base_price: float
    subcategory_id: int
    subcategory_name: str
    category_id: int
    category_name: str
    service_id: int
    service_name: str
    in_inventory: bool   # True iff a storeinventory row exists for (store_id, product_id), regardless of is_available
```

## 5. Frontend

### 5.1 Route layout

```
/seller/inventory          (existing — single-row CRUD, unchanged)
/seller/inventory/bulk     (new — bulk editor)
```

Existing page gets a "Bulk edit" link in toolbar that navigates to `/seller/inventory/bulk`. Bulk page has "Back to single edit" link.

### 5.2 Bulk page layout (desktop)

```
┌──────────────────────────────────────────────────────────────────────┐
│ Toolbar: [Back] [+ Add products] [Bulk-fill ▾] [Save N changes]     │
│ Status:  3 new · 2 edited · 1 invalid                                │
├──────────────────────────────────────────────────────────────────────┤
│ ☐ │ Product           │ Service  │ Category   │ Price  │ Stock │ Avl │
│ ☐ │ Aashirvaad Atta…  │ Grocery  │ Staples    │ [275 ] │ [50 ] │ ✓   │
│ ☐ │ Tata Salt 1kg     │ Grocery  │ Staples    │ [22  ] │ [120] │ ✓   │
│ ☑ │ Maggi Noodles     │ Grocery  │ Snacks     │ [   !]│ [10 ] │ ✓   │   ← invalid row red border
└──────────────────────────────────────────────────────────────────────┘
```

- First column: row checkbox (used for bulk-fill targeting).
- Cells edit inline. Dirty rows show subtle background highlight.
- Invalid cells show inline red text below the input.
- Footer status counts: new / edited / invalid / unchanged.

### 5.3 Components (new, under `frontend/src/app/(operator)/seller/inventory/bulk/`)

| File | Role |
|------|------|
| `page.tsx` | Page shell, data fetch, Save handler, dirty-state guard |
| `BulkInventorySheet.tsx` | The editable table (rows = inventory items + pending adds) |
| `EligibleProductPicker.tsx` | Side panel: filter by service/category/subcategory + search; multi-select; "Add N to sheet" |
| `BulkFillToolbar.tsx` | Dropdown: "Set price…", "Set stock…", "Adjust price ±%". Acts on checked rows. |
| `bulk.module.css` | Page styles using existing design tokens |

### 5.4 State model (page-local)

```ts
type SheetRow = {
  inventory_id: number | null;        // null = new row
  product_id: number;
  product_name: string;
  service_name: string;
  category_name: string;
  price: string;                      // string for editable input
  stock: string;
  is_available: boolean;
  // derived
  dirty: boolean;
  errors: Partial<Record<"price" | "stock", string>>;
};
```

### 5.5 Validation rules (frontend)

- price: parsable float, `> 0`, `<= 999_999`
- stock: parsable int, `>= 0`
- product_id appears at most once
- Save button disabled while any row has errors OR no rows are dirty

### 5.6 Service-filter UX

Picker fetches from `GET /sellers/me/eligible-products`. Hierarchical sidebar collapsible by service → category → subcategory; each terminal node shows count. Already-in-inventory products are dimmed and disabled (`in_inventory: true`).

Fallback message when seller has no approved services: "You haven't been approved for any services yet. Contact admin." (Pre-empts an edge case where UI could otherwise look broken.)

### 5.7 Mobile

Below `768px`, the page renders a banner: **"Bulk editor works best on a wider screen. Open from a desktop browser to use it."** Below the banner the table renders horizontally scrollable (functional but not optimized). Single-row UX (`/seller/inventory`) remains the mobile path.

### 5.8 Dirty-state guard

Use Next.js `useEffect` on `beforeunload` to warn on tab close. Internal navigation guard via a confirm dialog before route change when unsaved rows exist.

## 6. Error handling

| Scenario | Response |
|----------|----------|
| Frontend validation fails | Save button disabled. Per-cell error message. Server never called. |
| Server validation fails (any row) | Server returns 4xx + per-row errors. Frontend marks those rows red; nothing saved (transaction rolled back). User fixes & retries. |
| Service-membership violation | 403 `SERVICE_NOT_APPROVED`. Row flagged; row's "Add" disabled until product removed from sheet. |
| Concurrent checkout decremented stock | Lock acquired in service; upsert re-reads stock and overwrites with seller's value (seller intent wins for stock field). |
| Network error | Toast error; sheet state preserved. Retry on user action. |
| Seller not approved (profile.status != approved) | Existing layout guard at `/seller/signup/pending` already blocks; bulk page inherits same dashboard layout. |

## 7. Testing

Backend (`backend/app/tests/test_inventory_bulk.py`, new file):

1. `test_bulk_upsert_creates_and_updates_atomically` — payload mixing new + existing products, both classes land in single commit.
2. `test_bulk_upsert_rejects_unapproved_service` — seller approved for Grocery only, payload includes a Pharmacy product → 403, zero rows persisted.
3. `test_bulk_upsert_rolls_back_on_invalid_row` — 5 valid + 1 invalid → transaction rolls back; pre-existing rows untouched.
4. `test_bulk_upsert_caps_at_200_rows` — 201 rows → 422 `ROW_LIMIT`.
5. `test_bulk_upsert_dedup_last_wins` — same product_id twice → single row, second value persists.
6. `test_eligible_products_filters_by_approved_services` — endpoint excludes products whose service isn't in `SellerProfileService`.
7. `test_eligible_products_marks_in_inventory_flag` — products already in store inventory flagged `in_inventory: true`.
8. `test_single_post_inventory_now_enforces_service_membership` — regression on existing endpoint.
9. `test_bulk_upsert_locks_existing_rows` — concurrent checkout test using existing pattern from `test_orders.py`.

Frontend: none (per CLAUDE.md, no frontend test infrastructure).

## 8. Out of scope (future work)

- CSV import/export (Q1 deferred)
- Bulk delete (Q3 deferred)
- Bulk add of *unlisted* (custom) products — sellers stay limited to admin master catalog.
- Per-product photos in bulk view — already covered by master catalog.
- Optimistic concurrency tokens (last-write-wins is fine for v1).

## 9. Migration / rollout

1. Ship backend endpoints behind no flag (additive — no breaking change to GET endpoints).
2. Existing single-row `POST /inventory` behavior changes: rejects new products outside approved services. Pre-existing `storeinventory` rows that would violate the new constraint are **grandfathered** — neither deleted nor surfaced as errors on update. Ship a one-shot management script (`backend/app/src/app/db/scripts/audit_inventory_service_membership.py`) the operator can run to log violations; not an Alembic migration (Alembic is for schema, not data audits).
3. Frontend page added; toolbar link in `/seller/inventory` reveals it.
4. Update `docs/flows.md` (inventory section) and `docs/development_guide.md` (testing patterns) with the new endpoint.

## 10. Open questions

None. All decisions locked above.
