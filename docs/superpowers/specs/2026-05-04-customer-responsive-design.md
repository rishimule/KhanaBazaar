# Customer Pages Responsive + Light Polish

**Date:** 2026-05-04
**Status:** Approved
**Scope:** Frontend customer-facing pages.

## Goal

Close remaining mobile gaps on customer pages, mirroring the breakpoints and polish from admin (PR #27) and seller (PR #28). Most customer pages were already responsive; only three need work.

## Pages with gaps

1. `frontend/src/app/account/orders/page.module.css` — same legacy template as old admin/seller orders list: hardcoded 1.5rem padding, no media queries, no tab scroll-x, grid minmax 280px squeezes below 320px.
2. `frontend/src/app/account/orders/[id]/page.module.css` — same legacy template as old admin/seller order detail: no media queries, header doesn't wrap on narrow viewports.
3. `frontend/src/app/cart/page.module.css` — cart row is a 5-column flex (emoji + info + qty + total + remove). On <480px the row gets cramped; qty controls and total need to stack below the name and stay touch-friendly.

Pages confirmed already responsive (no work needed): `/`, `/stores`, `/stores/[id]`, `/login`, `/sell`, `/account`, `/account/settings`.

Components confirmed already responsive from prior PRs: `DataTable`, `DataTableCard`, `StatsCard`, `DashboardLayout`, `OrderActionButtons`.

## Non-goals

- Visual reskin or new components.
- Backend or routing changes.
- Touching pages already responsive.

## Per-page changes

### `/account/orders` list
Apply the same template as `admin/orders/page.module.css` from PR #27:
- Page padding scaled at 768px / 480px.
- Tabs: scroll-x with hidden scrollbar at <768px, 44px touch height.
- Grid: 1-col below 480px.
- Title font-size scaled.

### `/account/orders/[id]` detail
Apply the same template as `admin/orders/[id]/page.module.css` from PR #27:
- Header wraps; title scales.
- Section padding tightens at 768px.
- Totals rows keep label/value alignment.

### `/cart`
- `<480px`: cart item row reflows. Emoji + name on top row; qty controls + total + remove on second row aligned spaced-between.
- `<480px`: total bar stacks label/value above the checkout button, which becomes full-width 44px.
- `<480px`: store group header stays single row (already wraps via gap).

## Breakpoints

Same as prior PRs: 768px primary, 480px mobile-S, 640px for action buttons.

## Testing

`npm run lint` (expect only pre-existing AuthContext error). `npm run build` clean. Manual sweep at 360 / 414 / 768 / 1024 px on the three pages.

## Risk

Low. CSS-only changes. Two pages clone proven admin/seller patterns; the cart change is bounded to a single page.
