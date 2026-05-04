# Seller Responsive + Light Polish Implementation Plan

**Goal:** Make `/seller/**` pages responsive at <480px, 480–768px, and desktop, mirroring admin PR #27.

**Architecture:** CSS-only changes plus opt-in `mobileCardRender` on the inventory `DataTable` (prop already exists from admin work). No backend, no routing.

**Tech Stack:** Next.js 16, React 19, CSS Modules, design tokens. Verification: `npm run lint`, `npm run build`, manual DevTools sweep at 360 / 414 / 768 / 1024 px.

**Spec:** `docs/superpowers/specs/2026-05-04-seller-responsive-design.md`
**Branch:** `feat/seller-responsive`

---

## Task 1: Inventory card mode + toolbar

**Files:**
- Modify `frontend/src/app/seller/inventory/page.tsx` (add `mobileCardRender` prop, import shared card styles)
- Modify `frontend/src/app/seller/inventory/page.module.css` (toolbar mobile-S rule)

Card layout: name + price right; subtitle = category; meta = stock count; status toggle full-width below.

Commit: `feat(seller): mobile card view for inventory + responsive toolbar`

## Task 2: Orders list responsive

**Files:**
- Modify `frontend/src/app/seller/orders/page.module.css` (tabs scroll-x, page padding scaled, grid 1-col `<480px`)

Pattern matches `admin/orders/page.module.css` written in PR #27.

Commit: `feat(seller): responsive orders list page`

## Task 3: Order detail responsive

**Files:**
- Modify `frontend/src/app/seller/orders/[id]/page.module.css` (header wrap, section padding, totals, mobile font sizing)

Pattern matches `admin/orders/[id]/page.module.css`. `OrderActionButtons` already stack at 640px (done in admin PR).

Commit: `feat(seller): responsive order detail page`

## Task 4: Signup wizard mobile

**Files:**
- Modify `frontend/src/app/seller/signup/seller-signup.module.css`
  - `<480px`: card padding `space-6 space-5`, stepDot 24px, cardTitle scaled to `2xl`, cardLogo to `4xl`, formGrid stays 1-col (already is).

Commit: `feat(seller): responsive signup wizard`

## Task 5: Pending page mobile

**Files:**
- Modify `frontend/src/app/seller/signup/pending/pending.module.css`
  - `<480px`: card padding `space-6 space-5`, title `xl`, icon `4xl`.

Commit: `feat(seller): responsive pending status page`

## Task 6: Final verification + PR

- `npm run lint` (expect only the pre-existing AuthContext error).
- `npm run build` clean.
- Manual sweep across all 5 pages at 360 / 414 / 768 / 1024 px.
- Push branch, open PR, squash-merge.
