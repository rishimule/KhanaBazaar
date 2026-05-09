<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Guest Browse + Cart Design

**Date:** 2026-05-06
**Branch (suggested):** `feat/guest-browse-cart`

## Problem

Guest users (not logged in) cannot browse stores. Visiting `/stores` or `/stores/[id]` redirects to `/login`. Industry norm (Instacart, Blinkit, Zepto) allows guests to browse and build a cart, deferring auth to checkout. Backend already exposes catalog and store reads as public endpoints, and `CartContext` already supports a guest-cart-to-server merge on login. The frontend is the only blocker.

## Goal

Let unauthenticated visitors:

1. Browse the store list (`/stores`).
2. Open any store detail page (`/stores/[id]`).
3. Add, update, remove items in a per-store cart (localStorage).
4. Visit `/cart` and review contents.
5. Be prompted to log in only when placing an order.

On successful login or signup, the guest cart must be merged into the customer's server-side cart, and the user must land back on the page they were trying to reach (e.g. `/checkout/[storeId]`).

## Non-goals

- No backend changes. Catalog reads, store reads, and `POST /api/v1/carts/sync` already support this flow.
- No new components or design system changes.
- No cart UI redesign.
- No address/profile collection during guest flow — captured at checkout post-login as today.

## Affected files

| File | Change |
|------|--------|
| `frontend/src/app/(customer)/[locale]/stores/page.tsx` | Drop login redirect; fetch `/api/v1/stores/` unconditionally. |
| `frontend/src/app/(customer)/[locale]/stores/[id]/page.tsx` | Drop login redirect; fetch store, inventory, catalog unconditionally. Remove now-unused `useAuth` import if applicable. |
| `frontend/src/app/(customer)/[locale]/login/page.tsx` | Honor `?next=` query param post-OTP-verify for customers; admin/seller continue using `getRedirect()`. Validate `next` is a same-origin path. |
| `frontend/src/lib/CartContext.tsx` | Surface `dropped` items from `syncCarts` response so the UI can notify the user. Smallest viable change: store last-sync drop count in context state, expose via `lastSyncDropped`. Page or layout consumes it and shows a toast. |
| `frontend/src/app/(customer)/[locale]/layout.tsx` (or equivalent customer shell) | Read `lastSyncDropped`; on transition from 0 → N, render a toast / banner: "N item(s) from your cart are no longer available". Auto-dismiss or one-shot. |

No new files required.

## Cart sync behavior (already implemented, documented for clarity)

`CartContext.tsx:75-114` runs on auth state transitions:

1. If `authLoading` → wait.
2. If no `dbUser` or non-customer role → load local cart and stop.
3. If customer logs in **and** local cart has items → call `POST /api/v1/carts/sync` with the local payload, replace state with response, clear `localStorage` `kb_carts`.
4. If customer logs in with empty local cart → just fetch their server-side cart.

Backend `carts.py:308-372` merges quantity-by-addition for items already present in the customer's server cart, and validates inventory:

- Unknown inventory ID → dropped with reason `unknown_inventory`
- Inventory not in declared store → dropped (caught by `inv.store_id != cart_payload.store_id`)
- Inventory exists but `is_available=false` → dropped with `item_unavailable`
- Whole store inactive → all items in payload dropped with `store_unavailable`

Dropped items are returned in `CartSyncResponse.dropped[]`. Today the frontend ignores this list.

## Login redirect logic

Login page currently calls `router.push(getRedirect(user))` after OTP success. `getRedirect` returns `/admin`, `/seller`, or `/stores`.

New behavior:

```ts
const params = useSearchParams();
const nextParam = params.get("next");

function safeNext(raw: string | null): string | null {
  if (!raw) return null;
  if (!raw.startsWith("/")) return null;        // must be path
  if (raw.startsWith("//")) return null;        // protocol-relative
  if (raw.includes("\\")) return null;          // backslash trick
  return raw;
}

const target =
  user.role === "customer"
    ? safeNext(nextParam) ?? getRedirect(user)
    : getRedirect(user);
router.push(target);
```

Same logic applies to both `verifyOtp` call sites in `login/page.tsx` (existing-user and new-user-with-name branches).

## Drop notification UX

Small but real: a guest who added an item that went out of stock between adding and logging in will silently lose it on sync today. Spec adds:

- `CartContext` keeps a `lastSyncDropped: number` state, default `0`.
- After successful sync, set it to `result.dropped.length`.
- Customer layout (or cart page) consumes it; if `> 0`, render a one-shot toast and reset to `0`.

Toast text: `"{count} item(s) from your guest cart were unavailable and removed."` Add i18n key `Cart.itemsDropped` to all locale files in `frontend/messages/` (en, hi, mr, gu, pa).

If a toast component does not already exist in the design system, use a top-of-page `role="status"` banner inside the customer layout. Do not add a new dependency.

## Edge cases

- **Logged-in seller/admin browsing customer pages:** `CartContext` already gates sync on `dbUser.role === "customer"`. They see localStorage cart only — unchanged.
- **Same user, two tabs:** localStorage `kb_carts` is shared. Both tabs reflect the same guest cart. After login, the tab that triggers login syncs; the other tab's stale `kb_carts` is empty after sync, so subsequent reads return `[]` from `localCart.getAllCarts()`. Acceptable for MVP.
- **`next` pointing to an external URL:** rejected by `safeNext`, falls back to `getRedirect`.
- **`next=/checkout/[storeId]` for a store the user's cart no longer covers (all items dropped):** checkout page already handles empty-cart state — shows empty message. No extra work.
- **Cart sync server error:** existing code does not catch. Today the user is left in a half-state (still has localStorage, no server cart). Spec keeps this behavior — out of scope. File a follow-up if needed.

## Test plan (manual, no frontend tests configured)

1. Open incognito → `/stores` loads, no redirect.
2. `/stores/[id]` loads, products visible, "Add" buttons work; localStorage `kb_carts` updates.
3. `/cart` shows items, "Login & checkout" link visible.
4. Click "Login & checkout" → URL is `/login?next=/checkout/[storeId]`.
5. Complete OTP → land on `/checkout/[storeId]` (next honored).
6. `GET /api/v1/carts` returns the merged cart; `localStorage.kb_carts` is gone.
7. Drop case: add an item, seller disables inventory in another browser, log in → toast shows "1 item …".
8. Open-redirect guard: hit `/login?next=https://evil.example` → after OTP, land on `/stores`, not the external URL.
9. Admin/seller login: their `?next=` is ignored; they go to `/admin` or `/seller` respectively.

## Risks

- **Existing behavior breakage:** none expected — public APIs already serve unauth requests.
- **CORS / cookie:** unchanged. `Authorization: Bearer` header pattern already conditional on token presence in `lib/api.ts`.
- **i18n string add:** new toast string requires entries across 5 languages (en, hi, mr, gu, pa). Acceptable, small.

## Out of scope (future work)

- Granular drop reporting (which products, which reason) — today we only show count.
- Anonymous server-side carts keyed by `kb_session_id` (would survive device change). Current localStorage-only approach is sufficient for MVP.
- Quantity-conflict resolution policy (today: additive). Could add a "max of guest vs remote" mode behind a setting.
