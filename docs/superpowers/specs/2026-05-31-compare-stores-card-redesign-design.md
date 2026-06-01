# Compare-nearby-stores card redesign

**Date:** 2026-05-31
**Status:** Approved (design)
**Area:** Checkout — price comparison section

## Problem

The checkout "Compare nearby stores" section currently renders two divergent UIs: an
HTML `<table>` on desktop (≥769px) and a card stack on mobile (≤768px), with per-card
"view item prices" expand toggles. It is functional but visually plain and inconsistent
across breakpoints. We want a single, polished card-grid UI matching the approved
mockup — source store and alternatives rendered as equal, equal-height cards with
always-visible item lists, real product images, an adaptive best-price banner, and
per-store delivery/summary detail.

## Goals

- One unified card-grid layout for all screen sizes (no separate desktop table).
- Render the **source store as a full card**, first in the grid, visually highlighted.
- Show item lists **always visible** (remove the per-card expand toggle).
- Real product images per item, with a branded placeholder fallback.
- Adaptive banner covering both "your store is cheapest" and "an alternative is cheaper".
- Keep all existing behavior: lazy fetch on section expand, `onShopAt` → `SwitchStoreDialog`,
  abort handling, gating, error/empty/loading states.

## Non-goals

- No change to the switch-store flow, dialog, or `replaceSubBasket` logic.
- No new sorting/filtering of alternatives (backend ordering preserved).
- No frontend tests (per project convention).
- Notification/compare copy stays English-only; keys still added to all locale files.

## Data change (backend)

The compare payload has no per-item image or category. Items render with the **real
product image** and fall back to the **category emoji** (reusing `ProductCard`'s
`CATEGORY_EMOJI` map keyed by `category_id`, fallback 📦). Add both fields:

- `backend/app/src/app/schemas/price_comparison.py` — add to `ComparisonItem`:
  - `image_url: Optional[str] = None`
  - `category_id: int`
- `backend/app/src/app/services/price_comparison.py` — fetch per-product
  `image_url` + `category_id` once, alongside the existing name localization (step 4):
  `select(MasterProduct.id, MasterProduct.image_url, Subcategory.category_id)` joining
  `MasterProduct.subcategory_id == Subcategory.id`, filtered to `product_ids`. Build a
  `meta_by_id: dict[int, tuple[str | None, int]]`. Populate `image_url` + `category_id`
  on **both** `ComparisonItem` construction paths (covered and imputed). The product is
  the same in both, so imputed items carry the same image/category. Import
  `MasterProduct` and `Subcategory` from `app.models.catalog`.
- `frontend/src/types/index.ts` — add `image_url: string | null` and
  `category_id: number` to `ComparisonItem`.

## Frontend changes

### Files
- `frontend/src/components/orders/PriceComparisonTable.tsx` — rewritten as a card-grid
  renderer. Remove the `<table>` block and the `MobileComparison` function (and its
  expand/`expandedIds` state). Keep/restyle `DeltaChip`. Add a `CompareStoreCard`
  (handles both source and alternative variants) and a `CompareItemImage` component
  (mirrors `ProductCard`'s `ProductImage`).
- `frontend/src/components/orders/PriceComparisonTable.module.css` — replaced with
  card-grid + card styles using design tokens.
- `frontend/src/components/orders/PriceComparison.tsx` — restyle the section header
  (toggle) into the icon + title + subhead + chevron layout; add the adaptive banner
  render when `status.kind === "loaded"`; add the footer note. Behavior unchanged.
- `frontend/src/components/orders/PriceComparison.module.css` — header, banner, footer
  styles.
- `frontend/messages/{en,hi,mr,gu,pa}.json` — new `Checkout.compare` keys (English
  copy in all five).

### Layout
- Card grid: CSS grid, `repeat(auto-fill, minmax(280px, 1fr))`, equal-height cards
  (`align-items: stretch`, internal flex column with the action button pinned to the
  bottom). Wraps to multiple rows when many stores. Single column on mobile. No
  horizontal scroll. Source card is always rendered first.

### Section header (in `PriceComparison.tsx` toggle)
Tag icon inside a tinted rounded square, "Compare nearby stores" title, subhead
"Same items, priced at {N} stores near you" (N = `alternatives.length`), collapse
chevron at the right. The whole header remains the expand/collapse control with
existing `aria-expanded`/`aria-controls` and lazy fetch.

### Adaptive banner
Rendered when loaded. Compute `cheapest = min(sourceSubtotal, min(alt.effective_total))`.
- If `sourceSubtotal <= every alt.effective_total` → **green** banner, shield icon.
  Copy (`bannerBest`): "You're getting the best price. **{source}** is the cheapest
  store nearby and ships your whole cart in one delivery." (The source store always
  ships the whole cart in one delivery, so this clause is unconditional.)
- Else (some alt cheaper) → **amber** banner, savings icon:
  "Save ₹{X} — **{store}** is cheaper for your cart." where `{store}` is the cheapest
  alt and `X = sourceSubtotal − cheapestAlt.effective_total`.

### Source card (highlighted)
Orange border + tinted background. "YOUR CART" pill overlapping the top edge.
Store-icon avatar, store name, "Your store" subtext. Big price = source subtotal
(`Σ price × quantity`). "Current store" chip. Green "Ships in one delivery" pill.
Divider. Item rows (image + name + line price; no "YOUR STORE" tags — all items are
its own). Disabled "✓ Selected" button pinned at bottom. No `DeltaChip`.

### Alternative card
Store-icon avatar, name, "{km} km away". Big price = `effective_total`. `DeltaChip`
(`+₹X more` amber / `Save ₹X` green / "Same total" neutral) vs `sourceSubtotal`.
Delivery pill: "Ships in one delivery" when `missing_count === 0`, else
"Arrives in 2 deliveries". Divider. Item rows: image + name + (when `item.imputed`)
a "YOUR STORE" tag + line price. Divider. Summary rows:
- "{covered_count} from this store" → `covered_subtotal` (when `covered_count > 0`)
- "{missing_count} from {source}" → `imputed_subtotal` (when `missing_count > 0`)

Outlined "Switch to this store" button pinned at bottom → existing `onShopAt(alt)`
(disabled via `shopDisabled`). `SwitchStoreDialog` unchanged.

### Item rows
- Price shown = `unit_price × quantity` line total; append "× N" suffix only when
  `quantity > 1`.
- `CompareItemImage`: mirror `ProductCard`'s image logic — `useState(imgFailed)`;
  `showImage = Boolean(image_url) && !imgFailed`; render
  `<img src={image_url} referrerPolicy="no-referrer" loading="lazy" onError={() => setImgFailed(true)}>`.
  When `!showImage`, render the category-emoji glyph span
  (`CATEGORY_EMOJI[category_id] ?? "📦"`). Define a shared `CATEGORY_EMOJI` constant in
  the component (same map as `ProductCard`); do not import across components for one
  small literal.

### Footer note
Below the grid: clock icon + "Prices and stock update in real time across nearby stores."

## i18n keys (`Checkout.compare`)

Add (English copy, mirrored into all five locale files):
- `headerTitle` = "Compare nearby stores"
- `headerSubhead` = "Same items, priced at {count} stores near you"
- `yourCartPill` = "Your cart"
- `currentStoreChip` = "Current store"
- `yourStoreItemTag` = "Your store"
- `shipsOneDelivery` = "Ships in one delivery"
- `arrivesTwoDeliveries` = "Arrives in 2 deliveries"
- `bannerBest` = "You're getting the best price. {store} is the cheapest store nearby and ships your whole cart in one delivery."
- `bannerSave` = "Save {amount} — {store} is cheaper for your cart."
- `summaryFromThisStore` = "{count} from this store"
- `summaryFromSource` = "{count} from {store}"
- `footerNote` = "Prices and stock update in real time across nearby stores."
- `selectedBtn` = "Selected"
- `yourStoreSubtext` = "Your store"

Reuse existing keys where present (`shopAt`, `kmAway`, `saveDelta`, `moreDelta`,
`sameTotal`, `toggleDisabledHint`, `loading`, `emptyState`, `retry`). Remove now-unused
keys only if confirmed dead (`viewItemPrices`, `hideItemPrices`, table-footer keys) —
verify no other consumer first.

## Tests

- Extend the existing compare tests (`app/tests/test_carts_compare.py`) — assert
  `image_url` and `category_id` are present and correct on both a covered item and an
  imputed item in the response.
- Backend lint/type: `uv run ruff check .`, `uv run mypy .`.
- Frontend: `npm run lint`, `npm run build`.

## Risks / notes

- Removing the desktop `<table>` removes a semantic-table a11y affordance; the card
  grid must keep accessible structure (cards as `<article aria-labelledby>`, banner with
  appropriate role, item images with `alt`, buttons labeled).
- `category_id` requires a `MasterProduct → Subcategory` join not currently in the
  service; fold it into the step-4 metadata query so it stays a single round-trip.
- Item images are remote (dev seed LoremFlickr URLs); keep `referrerPolicy="no-referrer"`
  to avoid leaking checkout paths to the CDN, consistent with `ProductCard`.
