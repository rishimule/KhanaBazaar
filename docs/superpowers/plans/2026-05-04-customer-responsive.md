<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Customer Responsive + Light Polish Plan

**Goal:** Make `/account/orders`, `/account/orders/[id]`, and `/cart` clean on mobile. Other customer pages already responsive.

**Branch:** `feat/customer-responsive`
**Spec:** `docs/superpowers/specs/2026-05-04-customer-responsive-design.md`

## Task 1: Account orders list

**File:** `frontend/src/app/account/orders/page.module.css`
Replace contents with the same template as `admin/orders/page.module.css` (PR #27), preserving the existing `.toast` class.

Commit: `feat(account): responsive orders list page`

## Task 2: Account order detail

**File:** `frontend/src/app/account/orders/[id]/page.module.css`
Replace contents with the same template as `admin/orders/[id]/page.module.css` (PR #27).

Commit: `feat(account): responsive order detail page`

## Task 3: Cart row + total bar mobile

**File:** `frontend/src/app/cart/page.module.css`
Append `@media (max-width: 480px)` rules:
- `.cartItem` flex-direction column or wrap; emoji + info on row 1; qty + total + remove on row 2 spaced.
- `.totalBar` flex-direction column, `.checkoutBtn` full-width 44px.
- `.storeGroupHeader` reduce padding.

Commit: `feat(cart): responsive cart row + total bar`

## Task 4: Verify, push, PR, merge

`npm run lint` + `npm run build`. Push, PR, squash-merge.
