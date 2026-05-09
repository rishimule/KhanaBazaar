<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Bulk Inventory Editor — Grouped by Service & Category

**Date:** 2026-05-05
**Scope:** `frontend/src/app/(operator)/seller/inventory/bulk/` — `page.tsx`, `BulkInventorySheet.tsx`, `EligibleProductPicker.tsx`, `bulk.module.css`. No backend changes.

## Problem

The bulk inventory editor renders every row in a single flat sheet with `Service` and `Category` columns repeated on every line. Once a seller has 30+ rows across multiple services, scanning is hard, and bulk operations don't have a natural per-service / per-category scope.

Goals:

1. Group sheet rows by **service** (tabs) then by **category** (sticky-anchored sections), matching the redesigned single-edit page.
2. Drop the `Service` column (now the active tab) and the `Category` column (now the section header). Keep the `Subcategory` column inside each per-category sheet.
3. Preserve all existing bulk behaviour — global selection, global save, global status counts, bulk-fill toolbar — so the editor remains a "one big workspace" mental model.
4. Add a per-category `+ Add` button that opens the existing picker pre-filtered to that category's eligible products.
5. Reuse `BulkFillToolbar` and `EligibleProductPicker` unchanged in interface; small additions to the picker for preset filters.

## Layout

```
+--------------------------------------------------------------+
| [← Single edit]   [+ Add products]   [Save N change(s)]      |
+--------------------------------------------------------------+
| 3 new · 5 edited · 0 invalid · 30 total                      |   <- status (global)
+--------------------------------------------------------------+
| Bulk fill toolbar (visible when ≥1 row selected)             |   <- global
+--------------------------------------------------------------+
| [ Grocery (24) ] [ Pharmacy (4) ] [ Food (2) ]               |   <- service tabs
+--------------------------------------------------------------+
| Fruits & Veg (12)  Dairy & Bakery (5)  Snacks (4)            |   <- sticky category nav
+--------------------------------------------------------------+
| ## Fruits & Vegetables (12)                       [+ Add]    |
| [✓] Product | Subcategory | Price | Stock | Avl | (Remove)   |
| ...rows...                                                    |
+--------------------------------------------------------------+
| ## Snacks (0)                                     [+ Add]    |
| (empty placeholder)                                           |
+--------------------------------------------------------------+
```

### Service tabs

- Derived from `store.services` (sorted by `sort_order`).
- Active service stored in URL: `?service=<slug>`. Defaults to first service. Falls back to first if the slug is unknown.
- Tab labels show count of `rows` in that service: `Grocery (24)`.
- Switching tabs is a non-destructive view filter — `rows`, `selectedIndices`, and dirty state are preserved untouched.

### Sticky category nav strip

- One anchor link per category in the active service.
- Each link: `<name> (<count>)` where count = rows in that category in the active service.
- Sticky to the scroll container's top (`.main` of `DashboardLayout`).
- Click → `scrollIntoView({ behavior: "smooth", block: "start" })`.

### Category sections

- One `<section id="cat-<categoryId>">` per category in the active service. All categories of the active service render, even those with zero rows.
- Header: category name + count + per-category `+ Add` button (opens picker with that category preset).
- Body: a `BulkInventorySheet` instance scoped to that category's rows. Shared `selectedIndices` / `onPatchRow` / `onRemoveRow` callbacks (using each row's original index in the global `rows` array).
- Empty category renders a single placeholder line: `No rows in this category yet — + Add` instead of an empty table.

### Columns inside each per-category sheet

| Column | Render |
|--------|--------|
| Select | Checkbox bound to `selectedIndices` |
| Product | `row.product_name` |
| Subcategory | `row.subcategory_name` |
| Price (₹) | Number input (with cell error display) |
| Stock | Number input (with cell error display) |
| Avl | Checkbox |
| Actions | `Remove` button (only for new rows, `inventory_id === null`) |

The current `Service` and `Category` columns are removed.

## Selection, save, and dirty state — all global

This is the load-bearing decision: **`rows`, `selectedIndices`, and dirty state never reset on tab/category switch.**

- Selecting a row in Grocery, then switching to Pharmacy, keeps the Grocery row selected.
- Bulk-fill applies to **every** selected row across services. The toolbar's `selectedCount` reflects the global selection.
- Status bar (`X new · Y edited · Z invalid · N total`) and the `Save` button operate over the whole sheet, unchanged.

## Data flow

The page state model is unchanged:

- `rows: SheetRow[]` — flat array, mutation order preserved.
- `selectedIndices: Set<number>` — original `rows` indices.
- `eligible`, `store`, `pickerOpen`, `saving`, `fetching` — unchanged.

New state:

- `pickerPreset: { serviceId: number; categoryId: number } | null` — when set, the picker mounts with these as the initial filter values.

A `useMemo` builds the bucket structure for rendering:

```ts
type CategoryBucket = {
  category_id: number;
  category_name: string;
  rows: Array<{ row: SheetRow; originalIndex: number }>;
};

type ServiceBucket = {
  service: Service;
  categories: CategoryBucket[];
  totalCount: number;
};
```

For each row in `rows`, push it to the matching service / category bucket along with its original index. Within each category bucket, sort by `subcategory_name` then `product_name`. Categories listed for each service come from the active store's `store.services` joined with `categories` fetched via `/api/v1/catalog/categories` (added to the existing fetch).

The active service is selected via `?service=<slug>` (default = first). If `activeBucket?.categories.length === 0`, render a "No categories in this service yet." notice.

## Component changes

### `page.tsx`

- Add `useSearchParams`, `usePathname` for URL state.
- Fetch `/api/v1/catalog/categories` alongside the existing parallel calls.
- Build the `ServiceBucket[]` memo as above.
- Add `pickerPreset` state.
- Render: toolbar → status bar → `BulkFillToolbar` → service tabs → sticky category nav → per-category sections → existing modal-style `EligibleProductPicker` (props extended with `initialServiceId` / `initialCategoryId`, see below).

### `BulkInventorySheet.tsx`

- Currently takes `rows: SheetRow[]` and uses array index as identity. Refactor so it takes:
  ```ts
  rows: Array<{ row: SheetRow; originalIndex: number }>
  ```
  and uses `originalIndex` for `onToggleSelect` / `onPatchRow` / `onRemoveRow` calls. The visible row index inside this sub-sheet is no longer load-bearing.
- Drop `Service` and `Category` `<th>`/`<td>` columns. Replace with a single `Subcategory` column.
- Empty placeholder no longer says "No rows. Click 'Add products'…" — that case is now handled per-category inside `page.tsx`. The component itself just returns the table; if `rows.length === 0`, return null (page renders the empty placeholder).

### `EligibleProductPicker.tsx`

- Accept new optional props:
  ```ts
  initialServiceId?: number | null;
  initialCategoryId?: number | null;
  ```
- Initialise `serviceId` / `categoryId` state from these on mount.
- When the picker is opened from a per-category `+ Add`, the dropdowns start at that service+category. User can still widen the filter inside the picker.

### `bulk.module.css`

New classes (mirroring the single-edit page styles where possible):

- `.serviceTabs`, `.serviceTab`, `.serviceTabActive`, `.serviceTabCount`
- `.categoryNav`, `.categoryNavLink`, `.categoryNavCount`
- `.categorySection`, `.categoryHeader`, `.categoryTitle`, `.categoryCount`, `.categoryAddBtn`, `.emptyCategory`
- `.servicesEmpty` (used for "no services" + "no categories")

Existing `.sheetWrap`, `.sheet`, `.cell`, `.cellErr`, `.cellErrMsg`, `.rowNew`, `.rowDirty`, `.empty` retained.

## URL state

- `?service=<slug>` — active tab. Updated via `router.replace(...)` on tab click; no scroll reset.
- Category anchors `#cat-<id>` — pure in-page jumps, not persisted.

## Edge cases

| Case | Behaviour |
|------|-----------|
| Store has no services | Render notice: "No services linked to this store. Contact admin." Hide tabs / sections. The "+ Add products" toolbar button stays disabled (existing `disabled={!store}` already covers it). |
| Active service has no categories | Render notice: "No categories in this service yet." |
| Category has zero rows | Inline empty placeholder: "No rows in this category yet — + Add". The category still appears in the nav strip with `(0)`. |
| Row whose product's category isn't in the active store's `services` | Drop silently from view (defensive — backend guarantees this can't happen for eligible products). The row is still kept in `rows` array — the user just can't see it. Same trade-off as on the single-edit page. |
| `?service=<slug>` slug not in `store.services` | Fall back to first service. |
| Selection across hidden rows | Hidden rows (e.g., row whose category isn't in current store services) cannot be re-selected from UI. Existing selections persist in the set; bulk-fill still applies. Acceptable. |

## Out of scope

- Per-tab status counts (e.g., `Grocery (3 dirty)`). Status bar is global; tab-level dirty badges add visual noise.
- Drag reorder, virtualisation, undo. Existing behaviour is fine for the scale of master catalogs.
- Mobile redesign. Existing `.mobileBanner` already routes mobile users to single-edit; bulk page remains desktop-first.

## Files touched

- `frontend/src/app/(operator)/seller/inventory/bulk/page.tsx` — bucketing, tabs, nav strip, category sections, picker preset wiring, fetch categories.
- `frontend/src/app/(operator)/seller/inventory/bulk/BulkInventorySheet.tsx` — accept `{row, originalIndex}[]`; drop service/category columns; null-return on empty.
- `frontend/src/app/(operator)/seller/inventory/bulk/EligibleProductPicker.tsx` — accept `initialServiceId`/`initialCategoryId` props.
- `frontend/src/app/(operator)/seller/inventory/bulk/bulk.module.css` — new section/tab/nav classes.

No backend changes. No new dependencies.
