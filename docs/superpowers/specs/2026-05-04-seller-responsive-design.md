<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Seller Responsive + Light Polish

**Date:** 2026-05-04
**Status:** Approved
**Scope:** Frontend `frontend/src/app/seller/**` plus the inventory consumer of `DataTable`.

## Goal

Make every seller page work cleanly on mobile (<480px), tablet (480–1024px), and desktop. Reuse the `mobileCardRender` prop on `DataTable` (added in admin PR #27) and the same breakpoint conventions. No backend changes.

## Non-goals

- Visual reskin or new components.
- Copy / wording changes in the wizard.
- Backend, routing, or new auth behavior.

## Affected files

- `frontend/src/app/seller/inventory/page.tsx`
- `frontend/src/app/seller/inventory/page.module.css`
- `frontend/src/app/seller/orders/page.module.css`
- `frontend/src/app/seller/orders/[id]/page.module.css`
- `frontend/src/app/seller/signup/seller-signup.module.css`
- `frontend/src/app/seller/signup/pending/pending.module.css`

Already done in admin PR #27 (no further changes needed): `seller/page.module.css` (dashboard), `DataTable`, `DataTableCard.module.css`, shared `OrderActionButtons.module.css`, `DashboardLayout.module.css`, `StatsCard.module.css`.

## Breakpoints

Same as admin: 768px primary, 480px mobile-S, 640px for action-button stack.

## Per-page changes

### `/seller/inventory`
- Toolbar mobile-S rule: stretch column, full-width add button (44px touch target).
- Pass `mobileCardRender` to DataTable. Card layout:
  - Top row: product name + price (right-aligned).
  - Subtitle: category.
  - Meta: stock count.
  - Status toggle (Available/Unavailable) full-width below.

### `/seller/orders`
- Tabs: scroll-x on overflow, hide scrollbar.
- Page padding scaled at 768/480.
- Grid `1fr` on `<480px` so cards never squeeze below 280px.

### `/seller/orders/[id]`
- Same template as admin order detail: header wrap, tighter section padding, scaled title.

### `/seller/signup` wizard
- Card padding: `space-10 space-8` → `space-6 space-5` `<480px`.
- Step indicator: dot 32px → 24px `<480px`; label `xs` → `2xs` (or hide labels, keep dots).
- Title font-size scaled.

### `/seller/signup/pending`
- Card padding scaled `<480px`.
- CTA button keeps full-width (already is).

## Implementation order

1. Inventory card mode + toolbar.
2. Orders list responsive.
3. Order detail responsive.
4. Signup wizard mobile.
5. Pending page mobile.

## Testing

Manual sweep at 360 / 414 / 768 / 1024px. `npm run lint` + `npm run build` clean.

## Risk

Low. CSS-only + 1 new card render. Reuses existing infra from admin PR.
