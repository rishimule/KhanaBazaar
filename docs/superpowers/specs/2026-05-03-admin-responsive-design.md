<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Admin Responsive + Light Polish

**Date:** 2026-05-03
**Status:** Approved (design)
**Scope:** Frontend admin section only (`frontend/src/app/admin/**`, supporting components).

## Goal

Make all admin pages work cleanly on mobile (<480px), tablet (480–1024px), and desktop (>1024px). Apply light visual polish (consistent spacing, badges, buttons, shadows) without changing the admin look. No backend changes. No reskin to shadcn.

## Non-goals

- New color palette, fonts, or icons.
- Migration off CSS Modules.
- Customer- or seller-side pages.
- New admin features or routes.

## Affected files

### Pages
- `frontend/src/app/admin/layout.tsx`
- `frontend/src/app/admin/page.tsx` (dashboard)
- `frontend/src/app/admin/categories/page.tsx`
- `frontend/src/app/admin/products/page.tsx` + `page.module.css`
- `frontend/src/app/admin/orders/page.tsx` + `page.module.css`
- `frontend/src/app/admin/orders/[id]/page.tsx` + `page.module.css`
- `frontend/src/app/admin/sellers/page.tsx` + `page.module.css`

### Shared components
- `frontend/src/components/DashboardLayout.tsx` + `.module.css`
- `frontend/src/components/DataTable.tsx` + `.module.css`
- `frontend/src/components/StatsCard.module.css`
- `frontend/src/components/Modal.module.css` (mobile padding only if needed)

## Breakpoints

Use existing design tokens. Standard media queries:

| Range | Label | Behavior |
|-------|-------|----------|
| `<480px` | mobile-S | Single column. Stacked toolbar. Full-width buttons. |
| `480–768px` | mobile-L / tablet-S | Single column, slightly tighter padding. |
| `768–1024px` | tablet | 2-col grids, sidebar slides over content (existing). |
| `>1024px` | desktop | Current layout, no changes. |

Primary breakpoint constant in CSS: `768px` (already used). Add `480px` where mobile-S diverges.

## Component changes

### DataTable — mobile card mode (opt-in)

Add prop:

```ts
mobileCardRender?: (row: T) => ReactNode;
mobileBreakpoint?: number; // default 768
```

Behavior:
- When `mobileCardRender` is supplied and viewport `<= mobileBreakpoint`, render a vertical list of cards instead of `<table>`.
- Detection: CSS-only via media query (preferred) — render both, hide table or cards via `display: none`. No JS resize listener.
- When prop is omitted, fall back to current horizontal-scroll behavior (no regression on pages that don't opt in).

Card row baseline styling (in `DataTable.module.css`): rounded card, `shadow-sm`, padded, `gap` between rows. Page passes content; component handles wrapping.

### DashboardLayout
- Confirm hamburger reachable on `<480px`.
- Header padding reduced on mobile.
- Sidebar nav items: 44px min-height for touch.

### StatsCard
- Stack icon + text vertically on `<480px` if width pinch.
- Number font size scaled down one step on mobile.

### Modal
- Already full-width on mobile via existing CSS. Verify and tighten padding only if jarring.

## Per-page specs

### `/admin` dashboard
- StatsGrid: 4 cols → 2 cols `<1024px` → 1 col `<480px`.
- QuickActions: 3-up → 2-up `<768px` → 1-up `<480px`.
- ActiveOrdersWidget: width 100% on mobile, internal cards stack.

### `/admin/categories`
- Toolbar: count + filter + add button. Wrap; on `<480px`, add button full-width below filters.
- DataTable card render:
  - Top row: name (bold) + service badge.
  - Subtitle: description (clamped 2 lines).
  - Meta: product count.
  - Actions: edit + delete inline at bottom.

### `/admin/products`
- Toolbar: same pattern.
- DataTable card render:
  - Top row: product name + base price (right-aligned).
  - Subtitle: category badge + description (clamped 2 lines).
  - Actions: edit + delete.

### `/admin/orders`
- Page padding: `1.5rem` desktop → `1rem` `<768px` → `0.75rem` `<480px`.
- Tabs (active/history): horizontal scroll-snap on mobile if overflow; hide scrollbar.
- Card grid: `auto-fill, minmax(280px, 1fr)`; on `<480px`, full-width cards (`1fr`).

### `/admin/orders/[id]`
- Sections stack (already do).
- Header: title + status badge wrap; status badge on its own line `<480px`.
- Totals rows: keep right-alignment; wrap label/value if narrow.
- Action buttons: full-width and stacked `<640px`.

### `/admin/sellers`
- Toolbar tabs: horizontal scroll if overflow on mobile.
- DataTable card render:
  - Top row: business name + status pill.
  - Subtitle: owner name + email.
  - Meta: services count, submitted date.
  - Action: review button full-width.
- Review modal:
  - `detailsGrid`: `1fr 1fr` desktop → `1fr` `<768px`.
  - Service picker grid: collapse to 1 col `<480px`.
  - Reject form: inputs full-width, buttons stack.

### `/admin/layout.tsx`
- Verify mobile header bar height + hamburger position.
- No structural change unless gap found.

## Polish (cross-page)

- **Shadows:** `shadow-sm` for cards/tables. `shadow-md` only on modal/sidebar overlay. Remove any `shadow-lg` from page-level cards.
- **Button heights:** 36px desktop, 44px mobile (touch target). Apply to primary, secondary, danger buttons used in admin.
- **Badge radius:** unify on `border-radius-pill` (already token).
- **Tab styling:** consistent across orders and sellers pages — same active indicator, same height.
- **Empty states:** verify each list page (categories, products, orders, sellers) has icon + title + subtitle + optional CTA, using the same pattern.

## Implementation order

1. DataTable mobile card mode (component + CSS).
2. Apply card render on categories, products, sellers pages.
3. Per-page CSS responsive sweep (orders list, order detail, dashboard).
4. Modal detailsGrid fix on sellers page.
5. Polish pass: shadows, button heights, badge radius.
6. Smoke test: dev server + DevTools mobile profiles (375x667, 414x896, 768x1024).

## Testing

- Manual: load each admin page in Chrome DevTools at 375px, 414px, 768px, 1024px, 1440px.
- Verify: no horizontal scroll on `<body>`, all CTAs reachable, modals fit viewport, no overlapping text.
- Lint + typecheck: `npm run lint` clean.
- No automated tests added (CSS-only + opt-in prop, low risk).

## Risk

Low.
- CSS-only changes for existing pages.
- DataTable change is additive (new optional prop), so no caller breaks.
- Desktop layout unchanged unless explicitly polished.

Rollback: revert per-page CSS commits independently if needed.
