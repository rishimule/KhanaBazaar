# Store Detail Page — Instacart-Style Service / Category / Subcategory Layout

**Date:** 2026-05-04
**Scope:** `frontend/src/app/stores/[id]/page.tsx` and supporting backend exposure of subcategory data.
**Out of scope:** Stores list page (`/stores`) grouping, search, sort, multi-store browsing. These are separate efforts.

## Problem

Today the store detail page lists every product in a single grid behind a flat row of category pills (`All`, `Fruits & Vegetables`, `Dairy & Bakery`, `Staples & Grains`, `Medicines`). This breaks down once a store sells across multiple services (e.g., a kirana store that also stocks medicines and household goods):

- Categories from different services sit beside each other with no visual separation, so the user cannot see at a glance which "department" they are in.
- There is no way to drill into a subcategory (e.g., `Leafy Greens` within `Fruits & Vegetables`), even though the schema already supports it.
- Browsing a single category requires changing tab and losing context of the rest of the store; there is no equivalent of Instacart's "shelves" view where a user can scan across the catalog.

The catalog hierarchy in the database is already **Service → Category → Subcategory → MasterProduct**, but the store page renders only one level of it.

## Goals

1. Show inventory grouped first by **Service**, then by **Category**, in stacked sections users can scroll through (Instacart-style shelves).
2. Provide a sticky **jump nav** that lets the user jump to any service or category without losing place.
3. Allow filtering down to a single **Subcategory** within a category when the user wants to narrow.
4. Keep the page usable on mobile; do not regress existing add-to-cart, stock, or pricing affordances.

## Non-goals

- Search across products (the home page already has a global search; this work doesn't change that).
- Sort controls (price, rating). Defer.
- Cross-store comparison.
- Per-subcategory image cards (Instacart's "Browse by category" mosaic). Defer to a follow-up if useful.

## High-level UX

```
┌─ Store header (existing) ─────────────────────────────────────────────────┐
│  🏪  Sharma General Store         · Open Now                              │
│  12, MG Road, Sector 14, Gurugram                                          │
└────────────────────────────────────────────────────────────────────────────┘

┌─ Sticky jump nav ─────────────────────────────────────────────────────────┐
│  [All]  [Grocery ▾]  [Pharmacy ▾]                                          │
│         Fruits & Vegetables · Dairy & Bakery · Staples & Grains            │
└────────────────────────────────────────────────────────────────────────────┘

╭─ Grocery ──────────────────────────────────────────────────────────────────╮
│                                                                            │
│  Fruits & Vegetables                                              See all →│
│  ┌─[Leafy Greens]─[Roots]─[Fruits]─[Herbs]─┐                              │
│  │ Subcategory chips (sticky in section)   │                              │
│  └──────────────────────────────────────────┘                              │
│  [Spinach]   [Coriander]   [Methi]   [Bananas]                            │
│                                                                            │
│  Dairy & Bakery                                                   See all →│
│  [Subcategory chips]                                                      │
│  [Milk]   [Curd]   [Bread]                                                │
│                                                                            │
╰────────────────────────────────────────────────────────────────────────────╯

╭─ Pharmacy ─────────────────────────────────────────────────────────────────╮
│  Medicines                                                        See all →│
│  [Subcategory chips]                                                      │
│  [Paracetamol]  [Crocin]  ...                                             │
╰────────────────────────────────────────────────────────────────────────────╯
```

### Behavior

- **Default view:** All sections stacked. User scrolls and grazes.
- **Jump nav:** Sticks under the page header. Clicking a service scrolls to its section; clicking a category in the secondary row scrolls to that category. Active state derives from `IntersectionObserver` watching the section headings.
- **Subcategory chips:** Inside each category section. Default = `All`. Selecting a chip filters that section's grid in place; other sections are untouched. Selection is local to the section (not URL-bound for v1).
- **Empty service / category:** Hidden. Only services and categories that have at least one in-stock product are rendered.
- **Out-of-stock products:** Continue to render with the existing greyed-out state — same component.
- **Single-service store:** The service heading is suppressed (no value in showing one heading); only category sections render.

## Components

| Component | Responsibility |
|-----------|----------------|
| `StoreDetailPage` | Page-level state and data fetching. Builds the `Service → Category → Subcategory → InventoryItem[]` tree. |
| `StoreNav` | Sticky two-row jump nav. Row 1: services + `All`. Row 2: categories under the active service. |
| `ServiceShelf` | One service's set of category sections with the service heading (suppressed when only one service). |
| `CategorySection` | Heading, subcategory chip row, product grid. Owns its own subcategory filter state. |
| `SubcategoryChips` | Horizontal scroll row; pure presentational, controlled. |
| `ProductCard` | Existing — unchanged. |

`StoreDetailPage` does not pass mutable callbacks down deeply; each `CategorySection` is self-contained for filter state. The page only orchestrates fetch + tree-building.

## Data flow

On mount the page fetches in parallel:

- `GET /api/v1/stores/{id}`
- `GET /api/v1/stores/{id}/inventory`
- `GET /api/v1/catalog/services`
- `GET /api/v1/catalog/categories`
- `GET /api/v1/catalog/subcategories` *(new — see Backend changes)*
- `GET /api/v1/catalog/products`

The page joins these client-side into a tree:

```ts
type Tree = ServiceNode[];
interface ServiceNode { service: Service; categories: CategoryNode[]; }
interface CategoryNode { category: Category; subcategories: SubcategoryNode[]; items: InventoryWithProduct[]; }
interface SubcategoryNode { subcategory: Subcategory; items: InventoryWithProduct[]; }
```

Tree pruning rules:
- Drop subcategory nodes with zero items.
- Drop category nodes with zero items.
- Drop service nodes with zero categories.

## Backend changes

The `Subcategory` table exists in the schema, and `MasterProduct.subcategory_id` is a required foreign key — but the public catalog API today flattens products to `category_id` and never exposes subcategories. Two minimal additions are needed:

1. **Extend `ProductRead`** in `backend/app/src/app/api/catalog.py`:
   - Add `subcategory_id: int`
   - Add `subcategory_name: str` (English translation; falls back to slug)
   - `category_id` continues to come from the subcategory's parent (no schema change).
2. **Add `GET /api/v1/catalog/subcategories`** returning `[{ id, name, category_id, slug }]` for all subcategories, ordered by `(category_id, sort_order, id)`. English translation joined with the same fallback pattern used by `list_categories`.

No alembic migration is required — these changes are read-only API surface.

### Tests

Add to `backend/app/tests/test_catalog.py` (or whichever test file already exercises catalog endpoints; create one if absent):
- `GET /catalog/subcategories` returns subcategories belonging to the seeded categories.
- `GET /catalog/products` includes `subcategory_id` and `subcategory_name` on every item.

## Frontend changes

### Types (`frontend/src/types/index.ts`)

```ts
export interface Subcategory extends BaseSchema {
  name: string;
  category_id: number;
  slug: string;
}

export interface MasterProduct extends BaseSchema {
  name: string;
  description: string;
  category_id: number;
  subcategory_id: number;        // new
  subcategory_name: string;      // new
  image_url?: string;
  base_price: number;
}
```

### Page (`frontend/src/app/stores/[id]/page.tsx`)

- Replace the `activeCategory` flat-filter logic with the tree-building logic above.
- Render `<StoreNav>` followed by `<ServiceShelf>` per service node.
- The single-service short-circuit (suppress service heading when only one service exists) lives in `StoreDetailPage`, not in `ServiceShelf`, to keep the shelf component free of cross-cutting knowledge.

### Styling (`page.module.css`)

Carry over the existing card/grid tokens. New rules needed:

- `.stickyNav` — `position: sticky; top: <navbar-offset>;` two stacked rows, horizontal-scroll on overflow.
- `.serviceHeading`, `.categoryHeading` — typographic hierarchy. Service heading is larger than category heading.
- `.subcategoryChips` — horizontal scroll row, pill style consistent with current tab pills.
- Mobile: 2-col grid; ≥640 px: 3-col; ≥1024 px: 4-col (matches current). No change to card sizing.

### Accessibility

- Jump nav items are `<a href="#service-{id}">` / `<a href="#category-{id}">` with `aria-current="true"` when active so keyboard users get correct semantics, not just visual.
- Each section heading is `<h2>` (service) / `<h3>` (category), `id`-anchored to match the nav links.
- Subcategory chips are `<button>` with `aria-pressed`.

## Error handling

- If `/catalog/subcategories` 404s or fails (e.g., older backend), the page falls back to the previous flat behavior: render category sections without subcategory chips. This keeps the frontend deployable ahead of the backend change without a hard break.
- Other fetch failures continue to land in the existing `setStore(null)` "Store Not Found" path; this is unchanged.

## Manual verification

1. Open a store with products spanning multiple services — confirm two service headings, jump nav has both, scrolling updates the active state.
2. Open a single-service store — confirm no service heading, only category sections.
3. Open a category, click a subcategory chip — confirm only that section filters, others remain unchanged.
4. Add a product to cart from a filtered subcategory section — confirm cart still scopes to the store correctly.
5. Resize from desktop → tablet → mobile — confirm grid columns reflow, sticky nav stays under main navbar, chips horizontal-scroll cleanly.

## Risk / rollback

- The change is contained to one page plus two read-only API additions. Rollback = revert the PR. No data migration, no schema change.
- The frontend's graceful fallback means the page still renders even if the new subcategory endpoint is missing.
