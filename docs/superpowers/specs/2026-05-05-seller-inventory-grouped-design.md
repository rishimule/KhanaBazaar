# Seller Inventory — Grouped by Service & Category

**Date:** 2026-05-05
**Scope:** `frontend/src/app/(operator)/seller/inventory/page.tsx` and CSS module. No backend changes.

## Problem

Seller's inventory page renders all products in a single flat table with a `Category` column. Once a seller carries products across multiple services (Grocery, Pharmacy, etc.) or many categories, the flat table becomes hard to scan, and the same `Fruits & Vegetables` label repeats on every row.

Goals:

1. Group products by **service**, then by **category**.
2. Replace the `Category` column with a `Subcategory` column inside the per-category table (more granular, less repetition).
3. Keep existing behaviour: add product, edit price/stock, toggle availability, delete, bulk edit link.
4. Reuse existing components (`DataTable`, `Modal`, `DashboardLayout`).

## Layout

```
+--------------------------------------------------------------+
| Inventory Management                                         |
| 30 products in store         [Bulk edit →]   [+ Add Product] |
+--------------------------------------------------------------+
| [ Grocery (24) ]  [ Pharmacy (4) ]  [ Food (2) ]   <- tabs   |
+--------------------------------------------------------------+
| Fruits & Veg (12)  Dairy & Bakery (5)  Snacks (4)  ...       |   <- sticky anchor strip
+--------------------------------------------------------------+
| ## Fruits & Vegetables (12)                       [+ Add]    |
| Product | Subcategory | Price | Stock | Status | Actions      |
| ...table rows...                                              |
+--------------------------------------------------------------+
| ## Dairy & Bakery (5)                             [+ Add]    |
| ...table rows...                                              |
+--------------------------------------------------------------+
| ## Snacks (0)                                     [+ Add]    |
| (empty placeholder: "No products in this category yet")      |
+--------------------------------------------------------------+
```

### Active service selection

- Service tabs derived from `store.services` (ordered by `sort_order`).
- Active service stored in URL: `?service=<slug>`. Defaults to first service.
- Tab labels show count of inventory items in that service.
- If URL slug is not in `store.services`, fall back to first.

### Category sections

- One `<section id="cat-{categoryId}">` per category belonging to the active service.
- Header: category name + count + a small `+ Add` button (opens Add modal pre-filtered to that category).
- Body: `DataTable` with columns `Product | Subcategory | Price (₹) | Stock | Status | Actions`. Rows sorted by `subcategory_name` asc, then `product.name` asc.
- Empty category renders a single placeholder row with CTA instead of an empty table.

### Sticky category nav strip

- Renders anchor links to each category section in the active service.
- Sticky to viewport top (below the dashboard navbar).
- Each link: category name + count.
- Horizontal scroll on mobile.
- Click → `scrollIntoView({ behavior: "smooth", block: "start" })`.

## Data flow

On mount, fetch in parallel:

| Endpoint | Reason |
|----------|--------|
| `GET /api/v1/stores/my` | Current store + linked services (`store.services` already returns full `Service` objects). |
| `GET /api/v1/catalog/categories` | All categories with `service_id`. |
| `GET /api/v1/catalog/products` | Master products with `subcategory_name`. |
| `GET /api/v1/stores/{id}/inventory/all` | Seller inventory rows. |

No extra `/catalog/services` request — `store.services` is the source of truth for which service tabs to render.

Reduce to:

```ts
type Bucket = {
  service: Service;
  categories: Array<{
    category: Category;
    items: InventoryWithProduct[];
  }>;
};
```

Built once via `useMemo` over `[inventory, allProducts, categories, store.services]`.

## Components (new, all in the same page file unless noted)

- `InventoryServiceTabs({ services, counts, activeId, onChange })` — pill tabs with counts.
- `InventoryCategoryNav({ categories, counts })` — sticky anchor strip.
- `InventoryCategorySection({ category, items, onAdd, onEdit, onDelete, onToggle })` — header + DataTable or empty placeholder.

Existing reused components:

- `DataTable` for table rendering (already supports `mobileCardRender`).
- `Modal` for Add/Edit (unchanged behaviour).

The Add modal accepts an optional `presetCategoryId`. When set, the product dropdown filters to products whose `category_id` matches; otherwise it lists all `availableProducts` (current behaviour).

## Columns inside per-category table

| Column | Render |
|--------|--------|
| Product | `<strong>{product.name}</strong>` |
| Subcategory | `product.subcategory_name` |
| Price (₹) | `₹{price}` |
| Stock | `{stock}` |
| Status | Toggle button (Available / Unavailable) — unchanged behaviour |
| Actions | Edit + Delete (provided by `DataTable`) |

Mobile card render: title = product name, right = price, meta = `{subcategory_name} • Stock: {stock}`, then full-width Available toggle. (Replaces today's category meta.)

## URL state

- `?service=<slug>` — active service tab. Updated via `router.replace` on tab click (no scroll reset).
- Category anchors are pure `#cat-<id>` for in-page jump only; not persisted.

## Edge cases

| Case | Behaviour |
|------|-----------|
| Store has no services | Render notice: "No services linked to this store. Contact admin." Hide tabs/sections. |
| Active service has no categories | Render notice: "No categories in this service yet." |
| Category has zero inventory rows | Empty placeholder with `+ Add` CTA; section still listed in nav strip with `(0)`. |
| Inventory item whose product's category does not belong to any of `store.services` | Bucket under a synthetic `Other` tab labelled "Other" (defensive — should be impossible by backend rules). |
| `?service=` slug missing from `store.services` | Fall back to first service. |
| Loading | Single full-page "Loading…" — same as today. |

## Out of scope

- Global search across categories (Ctrl+F still works since all sections are open).
- Drag-to-reorder, bulk select, per-row image. Bulk edit remains its own page.
- Backend changes — none.

## Files touched

- `frontend/src/app/(operator)/seller/inventory/page.tsx` — main rewrite; keep handlers (`handleEdit`, `handleSaveEdit`, `handleDelete`, `handleAdd`, `toggleAvailability`).
- `frontend/src/app/(operator)/seller/inventory/page.module.css` — new classes for tabs, nav strip, category section header, empty placeholder. Existing `toggleBtn`/`toggleActive`/`toggleInactive`/`addBtn` retained.

No new top-level dependencies. Uses existing `next/navigation` `useSearchParams` + `useRouter` for `?service=`.
