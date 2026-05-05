# Single-Edit Add Product Modal — Always-Open Add + Search

**Date:** 2026-05-05
**Scope:** `frontend/src/app/(operator)/seller/inventory/page.tsx`. No backend changes.

## Problem

Two issues on the single-edit inventory page's per-category Add flow:

1. **Per-category `+ Add` button gets disabled** when every master product in that category is already in the seller's inventory. Sellers reported the disabled state being confusing — they expected to click and see *something*, even if it was just a notice.
2. **Add Product modal uses a plain `<select>` dropdown** with no search. Once a category has many master products, scrolling the dropdown is slow.

Goals:

1. Per-category `+ Add` buttons (header and empty-placeholder) are always enabled. Modal handles the empty case with an inline message + "Show all products" escape hatch.
2. Add Product modal gains a search input that filters products by name. Search composes with the existing `presetCategoryId` filter.

## Per-category Add — always enabled

- Drop the `disabled={availableProducts.filter(p => p.category_id === bucket.category.id).length === 0}` on both the header `+ Add` and the empty-placeholder `+ Add`.
- Global toolbar `+ Add Product` button retains `disabled={availableProducts.length === 0}` (rare — covers the "every master product already added" edge case for the entire store, where there's nothing to do anywhere).
- `openAdd(categoryId?)` opens the modal regardless of pool size.

## Modal — search + filtered list

The current modal uses a `<select>` of products. Replace it with:

- A text input above the list, `type="search"`, `placeholder="Search products…"`.
- A scrollable list below, one clickable row per product. Selected row highlighted.
- Search is case-insensitive substring match against `product.name`. Trims whitespace.
- Search composes with the existing `presetCategoryId` filter — i.e. when opened from a per-category `+ Add`, the list starts narrowed to that category, and search narrows further within it.

### Empty state — preset category exhausted

When a per-category `+ Add` opens the modal and the filtered list is empty:

- Show inline notice: "All products in this category are already in your inventory."
- Below it, a button: "Show all products" — clicking it sets the modal's local "show all" flag, which causes the list to ignore `presetCategoryId` and show every available product.
- The "show all" flag is local to the modal; closing/reopening resets it.

### Filter composition

The visible list is the result of, in order:

1. Start with `availableProducts` (master catalog minus rows already in inventory).
2. If `presetCategoryId !== null` and "Show all" is OFF → keep only `p.category_id === presetCategoryId`.
3. Apply search filter (substring match on name, case-insensitive, ignores empty/whitespace queries).

### Empty state — search yields nothing

When `availableProducts` (filtered by preset and "show all") is non-empty but the search query filters everything out:

- Show inline notice: "No products match {query}." No "show all" button (search is the constraint, not the preset).

### Empty state — entire store catalog exhausted

When `availableProducts.length === 0` (no preset, no search), the modal can still be opened from the per-category Add (since we removed the disable). Same notice as the preset-exhausted case but worded: "All available products are already in your inventory." No "Show all" button (it's already showing all).

## Selection model

- The product list is single-select (matching today's modal). Click a row → it becomes the selected product. The `Add Product` button at the bottom is disabled until a product is selected.
- Existing `formProductId` state continues to track the selected product. Clicking a row calls `setFormProductId(product.id)`.
- When the preset is set, the first product in the filtered list is auto-selected on open (matches today's behaviour for the `<select>` defaultValue).

## Component shape

The page component grows. Two small inline components keep the JSX legible:

- `AddProductList({ products, selectedId, onSelect })` — the scrollable list of clickable product rows. Replaces the `<select>`.
- `AddProductModalBody({ products, presetCategoryId, formProductId, setFormProductId, formPrice, setFormPrice, formStock, setFormStock })` — wraps the search input, "Show all" toggle, list, and the price/stock fields.

Both live in the same `page.tsx` file (the page is small and cohesive).

## Style

New CSS classes in `page.module.css`:

- `.searchInput` — full-width text input.
- `.productList` — scrollable container, max-height ~280px, border + radius.
- `.productListRow` — flex row, padding, hover state.
- `.productListRowSelected` — accent background for the currently selected row.
- `.productListEmpty` — italic muted notice text.
- `.showAllBtn` — link-style button used inside the empty notice.

## Files touched

- `frontend/src/app/(operator)/seller/inventory/page.tsx` — disable removal, modal rewrite, two inline components, "show all" state.
- `frontend/src/app/(operator)/seller/inventory/page.module.css` — new modal classes.

No new dependencies. No backend changes. No types changes.

## Out of scope

- Multi-select. Today's modal is single-select; keeping that.
- Server-side product search (master catalog is small enough to filter client-side).
- Mobile-specific tweaks beyond what existing styling covers.
