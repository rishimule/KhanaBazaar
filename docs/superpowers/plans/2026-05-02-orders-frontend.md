<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Orders — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the customer-facing order placement UX, role-specific order list and detail pages, "Active Orders" widgets in all three dashboards, and refactor the cart to a DB-backed store for logged-in users while keeping localStorage for guests.

**Architecture:** The cart context becomes auth-aware — guests use a `localCart` adapter that writes to localStorage, logged-in users use a `remoteCart` adapter that mirrors every operation to the backend with optimistic UI rollback on error. On login the context syncs localStorage → backend then clears localStorage. Order pages share a small set of role-aware components (`OrderCard`, `OrderTimeline`, `OrderActionButtons`, `OrderItemList`, `OrderStatusBadge`, `ActiveOrdersWidget`) driven by a single `lib/orders.ts` API client. Dashboards mount the widget; full pages live under `/account/orders`, `/seller/orders`, `/admin/orders`.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript, CSS Modules.

**Reference Spec:** `docs/superpowers/specs/2026-05-01-orders-design.md`
**Depends on:** `docs/superpowers/plans/2026-05-02-orders-backend.md` must be merged first.

---

## File Structure

### New files

- `frontend/src/lib/localCart.ts` — extracted guest cart (current `cart.ts` logic).
- `frontend/src/lib/remoteCart.ts` — typed API client matching `/api/v1/carts/*`.
- `frontend/src/lib/orders.ts` — typed API client matching `/api/v1/orders/*`.
- `frontend/src/components/orders/OrderStatusBadge.tsx` + `.module.css`.
- `frontend/src/components/orders/OrderTimeline.tsx` + `.module.css`.
- `frontend/src/components/orders/OrderItemList.tsx` + `.module.css`.
- `frontend/src/components/orders/OrderActionButtons.tsx` + `.module.css`.
- `frontend/src/components/orders/OrderCard.tsx` + `.module.css`.
- `frontend/src/components/orders/ActiveOrdersWidget.tsx` + `.module.css`.
- `frontend/src/components/orders/AddressPicker.tsx` + `.module.css`.
- `frontend/src/app/account/orders/page.tsx` + `.module.css`.
- `frontend/src/app/account/orders/[id]/page.tsx` + `.module.css`.
- `frontend/src/app/seller/orders/page.tsx` + `.module.css`.
- `frontend/src/app/seller/orders/[id]/page.tsx` + `.module.css`.
- `frontend/src/app/admin/orders/page.tsx` + `.module.css`.
- `frontend/src/app/admin/orders/[id]/page.tsx` + `.module.css`.
- `frontend/src/app/admin/page.tsx` (only if missing — check first; the layout already exists).

### Modified files

- `frontend/src/types/index.ts` — add `Order`, `OrderItem`, `OrderStatus`, `PaymentStatus`, `DeliveryStatus`, `CustomerAddress`-friendly types if missing; extend `CartItem` to include `inventory_id`.
- `frontend/src/lib/cart.ts` — shrink to shared helpers, re-export `localCart` + `remoteCart`.
- `frontend/src/lib/CartContext.tsx` — auth-aware backend selection, sync on login, optimistic updates with rollback.
- `frontend/src/components/ProductCard.tsx` (and any other add-to-cart call sites) — pass `inventory_id` when adding to cart.
- `frontend/src/app/cart/page.tsx` — enable checkout, mount `<AddressPicker />`, wire `placeOrders()`.
- `frontend/src/app/account/page.tsx` — mount `<ActiveOrdersWidget role="customer" />`.
- `frontend/src/app/seller/page.tsx` — mount `<ActiveOrdersWidget role="seller" />`.
- `frontend/src/app/admin/page.tsx` — mount `<ActiveOrdersWidget role="admin" />`.
- `frontend/src/components/DashboardLayout.tsx` — add an "Orders" nav entry to each role's `NAV` array (or extend the consumer pages that pass nav arrays — check the file first).
- `frontend/src/components/Navbar.tsx` — add an "Orders" link visible to logged-in customers.

### Out of scope

- Frontend test framework. None exists today.

---

## Task 1: Add type definitions

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Read the existing file**

```bash
sed -n '1,60p' frontend/src/types/index.ts
```

- [ ] **Step 2: Add the new types**

Append to `frontend/src/types/index.ts`:

```ts
export type OrderStatus = "pending" | "packed" | "dispatched" | "delivered" | "cancelled";
export type PaymentStatus = "pending" | "paid" | "failed" | "refunded";
export type DeliveryStatus = "pending" | "packed" | "dispatched" | "delivered" | "cancelled";
export type PaymentMethod = "cash" | "upi";

export interface OrderItem {
  id: number;
  inventory_id: number | null;
  product_name_snapshot: string;
  unit_price_snapshot: number;
  quantity: number;
  line_total: number;
}

export interface OrderPayment {
  method: PaymentMethod;
  status: PaymentStatus;
  amount: number;
  paid_at: string | null;
}

export interface OrderDelivery {
  status: DeliveryStatus;
  packed_at: string | null;
  dispatched_at: string | null;
  delivered_at: string | null;
}

export interface Order {
  id: number;
  store_id: number;
  store_name: string;
  customer_name?: string | null;
  status: OrderStatus;
  subtotal: number;
  delivery_fee: number;
  tax: number;
  total: number;
  placed_at: string;
  delivery_address_snapshot: string;
  items: OrderItem[];
  payment: OrderPayment;
  delivery: OrderDelivery;
}

export interface PlaceOrderResponse {
  orders: Order[];
}

export interface OrderListResponse {
  orders: Order[];
}
```

- [ ] **Step 3: Extend `CartItem`**

Find `CartItem` in the same file. Preserve any existing fields (likely `product_id`, `product_name`, `quantity`, `price`, `image_url?`) and add the two new optional/required fields the cart refactor needs:

```ts
export interface CartItem {
  product_id: number;
  inventory_id: number;             // NEW — required so DB cart writes know which inventory row
  product_name: string;
  quantity: number;
  price: number;
  image_url?: string;               // keep if already present
  id?: number;                      // NEW — populated only by remoteCart so the context can address rows
}
```

The `id?` field belongs here (not as a `declare module` augmentation later) so a single source of truth defines the type.

- [ ] **Step 4: Verify compile**

```bash
cd frontend && npx tsc --noEmit
```

Expected: type errors only at sites that build a `CartItem` without `inventory_id` — those are fixed in Task 4.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(types): add order types and inventory_id on CartItem"
```

---

## Task 2: Order API client

**Files:**
- Create: `frontend/src/lib/orders.ts`

- [ ] **Step 1: Create the file**

Create `frontend/src/lib/orders.ts`:

```ts
import { get, post } from "@/lib/api";
import type { Order, OrderListResponse, PlaceOrderResponse } from "@/types";

export async function listOrders(
  token: string,
  status?: "active" | "history"
): Promise<Order[]> {
  const path = status ? `/api/v1/orders?status=${status}` : "/api/v1/orders";
  const data = await get<OrderListResponse>(path, token);
  return data.orders;
}

export async function getOrder(token: string, orderId: number): Promise<Order> {
  return get<Order>(`/api/v1/orders/${orderId}`, token);
}

export async function placeOrder(
  token: string,
  customerAddressId: number
): Promise<Order[]> {
  const data = await post<PlaceOrderResponse>(
    "/api/v1/orders",
    { customer_address_id: customerAddressId },
    token
  );
  return data.orders;
}

export async function transitionOrder(
  token: string,
  orderId: number,
  to: "packed" | "dispatched" | "delivered"
): Promise<Order> {
  return post<Order>(`/api/v1/orders/${orderId}/transition`, { to }, token);
}

export async function cancelOrder(token: string, orderId: number): Promise<Order> {
  return post<Order>(`/api/v1/orders/${orderId}/cancel`, {}, token);
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/orders.ts
git commit -m "feat(orders): add order api client"
```

---

## Task 3: Cart API client (remoteCart)

**Files:**
- Create: `frontend/src/lib/remoteCart.ts`

- [ ] **Step 1: Create the file**

Create `frontend/src/lib/remoteCart.ts`:

```ts
import { del, get, patch, post } from "@/lib/api";
import type { Cart, CartItem } from "@/types";

interface RemoteCartItem {
  id: number;
  inventory_id: number;
  product_id: number;
  product_name: string;
  unit_price: number;
  quantity: number;
  line_total: number;
}

interface RemoteCart {
  store_id: number;
  store_name: string;
  items: RemoteCartItem[];
  subtotal: number;
}

interface RemoteCartListResponse {
  carts: RemoteCart[];
}

interface RemoteCartSyncResponse {
  carts: RemoteCart[];
  dropped: { inventory_id: number; reason: string }[];
}

function toCart(remote: RemoteCart): Cart {
  return {
    store_id: remote.store_id,
    store_name: remote.store_name,
    items: remote.items.map<CartItem>((item) => ({
      product_id: item.product_id,
      inventory_id: item.inventory_id,
      product_name: item.product_name,
      quantity: item.quantity,
      price: item.unit_price,
    })),
  };
}

export async function listCarts(token: string): Promise<Cart[]> {
  const data = await get<RemoteCartListResponse>("/api/v1/carts", token);
  return data.carts.map(toCart);
}

export async function addItem(
  token: string,
  storeId: number,
  inventoryId: number,
  quantity: number
): Promise<RemoteCartItem> {
  return post<RemoteCartItem>(
    "/api/v1/carts/items",
    { store_id: storeId, inventory_id: inventoryId, quantity },
    token
  );
}

export async function updateItemQty(
  token: string,
  itemId: number,
  quantity: number
): Promise<RemoteCartItem> {
  return patch<RemoteCartItem>(`/api/v1/carts/items/${itemId}`, { quantity }, token);
}

export async function removeItem(token: string, itemId: number): Promise<void> {
  await del<void>(`/api/v1/carts/items/${itemId}`, token);
}

export async function clearStoreCart(token: string, storeId: number): Promise<void> {
  await del<void>(`/api/v1/carts/${storeId}`, token);
}

export async function syncCarts(
  token: string,
  carts: { store_id: number; items: { inventory_id: number; quantity: number }[] }[]
): Promise<{ carts: Cart[]; dropped: { inventory_id: number; reason: string }[] }> {
  const data = await post<RemoteCartSyncResponse>("/api/v1/carts/sync", { carts }, token);
  return { carts: data.carts.map(toCart), dropped: data.dropped };
}
```

- [ ] **Step 2: Confirm `del` exists in `lib/api.ts`**

```bash
grep -n "export async function del" frontend/src/lib/api.ts
```

If missing, add it (mirror the `patch` shape, method `DELETE`, no body).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/remoteCart.ts frontend/src/lib/api.ts
git commit -m "feat(cart): add remoteCart api client"
```

---

## Task 4: Extract localCart and shrink cart.ts

**Files:**
- Create: `frontend/src/lib/localCart.ts`
- Modify: `frontend/src/lib/cart.ts`

- [ ] **Step 1: Create `localCart.ts` with the existing guest logic**

Create `frontend/src/lib/localCart.ts` — copy the full current `cart.ts` body verbatim (the localStorage logic). This file becomes the guest backend.

- [ ] **Step 2: List existing direct importers from `@/lib/cart`**

Before swapping the file, find every direct importer of the symbols this shim no longer re-exports as named exports:

```bash
grep -rn "from \"@/lib/cart\"" frontend/src | grep -v node_modules
grep -rn "from '@/lib/cart'" frontend/src | grep -v node_modules
```

Anything that imported `addToCart`, `removeFromCart`, `updateQuantity`, `clearCart`, `clearAllCarts`, `getCart`, `getAllCarts`, `getSessionId`, or `getCartCount` directly from `@/lib/cart` will break. The expected fix is to either:
- migrate that caller to `useCart()` from `CartContext` (preferred), or
- import from `@/lib/localCart` directly when the caller genuinely needs the localStorage layer (rare — only `CartContext`).

Capture the list; Step 3 commits the shim, Step 4 fixes the importers.

- [ ] **Step 3: Replace `cart.ts` with a thin shim**

Replace `frontend/src/lib/cart.ts` with:

```ts
/**
 * Cart shared helpers and re-exports.
 *
 * Pure helpers used by both guest (localCart) and authenticated (remoteCart) flows.
 */
import type { Cart } from "@/types";

export function getCartTotal(cart: Cart): number {
  return cart.items.reduce((sum, i) => i.price * i.quantity + sum, 0);
}

export function getGrandTotal(carts: Cart[]): number {
  return carts.reduce((sum, c) => sum + getCartTotal(c), 0);
}

export function getCartCount(carts: Cart[]): number {
  return carts.reduce((sum, c) => sum + c.items.reduce((s, i) => s + i.quantity, 0), 0);
}

// Re-export guest API for callers still using it directly (kept for
// backward compatibility during the refactor — preferred path is via
// CartContext).
export * as localCart from "@/lib/localCart";
```

- [ ] **Step 4: Update direct importers from Step 2**

For each file in the Step 2 grep output, switch to `useCart()` (or `import * as localCart from "@/lib/localCart"` if it really needs the raw guest module). Run `npx tsc --noEmit` between fixes to confirm progress.

- [ ] **Step 5: Update `localCart.ts` `addToCart` signature to accept the new `CartItem` shape**

Open `frontend/src/lib/localCart.ts` and confirm the `addToCart(storeId, storeName, item)` signature accepts the new `CartItem` shape (it will, because `CartItem` now requires `inventory_id`).

- [ ] **Step 6: Verify TypeScript still compiles for the shared helpers**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Errors should be limited to consumers (Task 5+).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/cart.ts frontend/src/lib/localCart.ts <fixed importers>
git commit -m "refactor(cart): split cart.ts into localCart adapter and shared helpers"
```

---

## Task 5: Pass `inventory_id` from add-to-cart call sites

**Files:**
- Modify: `frontend/src/components/ProductCard.tsx` (and any other component that builds a `CartItem`)

- [ ] **Step 1: Find all call sites**

```bash
grep -rn "addItem(" frontend/src/app frontend/src/components | grep -v "node_modules"
grep -rn "addToCart(" frontend/src/app frontend/src/components | grep -v "node_modules"
```

Each match needs to include `inventory_id` on the item object.

- [ ] **Step 2: Update `ProductCard.tsx` (canonical example)**

Find where `addItem` is called and confirm the `item` argument includes `inventory_id`. The product/inventory listing endpoint already returns `inventory_id` per the store inventory shape — pass it through. If `ProductCard` only receives a `MasterProduct`, lift the `inventory_id` from the parent `<StoreInventoryItem />` (or whatever the parent calls it). Pattern:

```tsx
// In the parent that owns inventory data:
<ProductCard
  product={{ ...product, inventory_id: inv.id, price: inv.price, stock: inv.stock }}
  storeId={storeId}
  storeName={storeName}
/>

// In ProductCard:
addItem(storeId, storeName, {
  product_id: product.id,
  inventory_id: product.inventory_id,
  product_name: product.name,
  price: product.price,
  quantity: 1,
});
```

- [ ] **Step 3: Verify all call sites updated**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Manually click "Add to cart" in a store page in the browser**

```bash
cd frontend && npm run dev
# Open http://localhost:3000/stores/<id>, add an item, open DevTools localStorage, confirm kb_carts entries now include inventory_id.
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ProductCard.tsx <other files>
git commit -m "feat(cart): include inventory_id when adding to cart"
```

---

## Task 6: Auth-aware CartContext with optimistic updates

**Files:**
- Modify: `frontend/src/lib/CartContext.tsx`

- [ ] **Step 1: Read the current file**

```bash
cat frontend/src/lib/CartContext.tsx
```

- [ ] **Step 2: Replace with the auth-aware version**

Replace the body of `frontend/src/lib/CartContext.tsx` with:

```tsx
"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useAuth } from "@/lib/AuthContext";
import * as localCart from "@/lib/localCart";
import * as remoteCart from "@/lib/remoteCart";
import { getCartCount, getCartTotal, getGrandTotal } from "@/lib/cart";
import type { Cart, CartItem } from "@/types";

interface CartContextValue {
  carts: Cart[];
  cartCount: number;
  loading: boolean;
  addItem: (storeId: number, storeName: string, item: CartItem) => Promise<void>;
  removeItem: (storeId: number, productId: number) => Promise<void>;
  updateQty: (storeId: number, productId: number, qty: number) => Promise<void>;
  clearStoreCart: (storeId: number) => Promise<void>;
  getTotal: (cart: Cart) => number;
  grandTotal: number;
}

const CartContext = createContext<CartContextValue | null>(null);

function findRemoteItemId(carts: Cart[], storeId: number, productId: number): number | undefined {
  const cart = carts.find((c) => c.store_id === storeId);
  return cart?.items.find((i) => i.product_id === productId)?.id;
}

export function CartProvider({ children }: { children: React.ReactNode }) {
  const { dbUser, token, loading: authLoading } = useAuth();
  const [carts, setCarts] = useState<Cart[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const lastSyncedUserId = useRef<number | null>(null);

  // Reset the sync sentinel whenever the active user disappears (logout) or
  // changes (account swap in same tab) so the next login re-syncs against
  // its own localStorage rather than the previous user's stale state.
  useEffect(() => {
    if (!dbUser) {
      lastSyncedUserId.current = null;
    }
  }, [dbUser]);

  const refreshLocal = useCallback(() => {
    setCarts(localCart.getAllCarts());
  }, []);

  const refreshRemote = useCallback(async () => {
    if (!token) return;
    const fresh = await remoteCart.listCarts(token);
    setCarts(fresh);
  }, [token]);

  // Initial load + auth transitions.
  useEffect(() => {
    if (authLoading) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      if (!dbUser || dbUser.role !== "customer" || !token) {
        // Guest mode.
        if (!cancelled) {
          refreshLocal();
          setLoading(false);
        }
        return;
      }
      // Customer mode. Sync local carts to backend on first transition for this user.
      try {
        if (lastSyncedUserId.current !== dbUser.id) {
          const local = localCart.getAllCarts();
          if (local.length > 0) {
            const payload = local.map((c) => ({
              store_id: c.store_id,
              items: c.items
                .filter((i) => typeof i.inventory_id === "number")
                .map((i) => ({ inventory_id: i.inventory_id, quantity: i.quantity })),
            }));
            const result = await remoteCart.syncCarts(token, payload);
            if (!cancelled) setCarts(result.carts);
            localCart.clearAllCarts();
          } else {
            await refreshRemote();
          }
          lastSyncedUserId.current = dbUser.id;
        } else {
          await refreshRemote();
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authLoading, dbUser, token, refreshLocal, refreshRemote]);

  const isCustomer = !!dbUser && dbUser.role === "customer" && !!token;

  const addItem = useCallback(
    async (storeId: number, storeName: string, item: CartItem) => {
      if (!isCustomer) {
        const updated = localCart.addToCart(storeId, storeName, item);
        setCarts(updated);
        return;
      }
      const previous = carts;
      // Optimistic: update local state first.
      setCarts((prev) => {
        const next = prev.map((c) => ({ ...c, items: [...c.items] }));
        let cart = next.find((c) => c.store_id === storeId);
        if (!cart) {
          cart = { store_id: storeId, store_name: storeName, items: [] };
          next.push(cart);
        }
        const existing = cart.items.find((i) => i.product_id === item.product_id);
        if (existing) {
          existing.quantity += item.quantity;
        } else {
          cart.items.push({ ...item });
        }
        return next;
      });
      try {
        await remoteCart.addItem(token!, storeId, item.inventory_id, item.quantity);
        await refreshRemote();
      } catch (err) {
        setCarts(previous);
        throw err;
      }
    },
    [carts, isCustomer, token, refreshRemote]
  );

  const removeItem = useCallback(
    async (storeId: number, productId: number) => {
      if (!isCustomer) {
        setCarts(localCart.removeFromCart(storeId, productId));
        return;
      }
      const previous = carts;
      const itemId = findRemoteItemId(carts, storeId, productId);
      setCarts((prev) =>
        prev
          .map((c) =>
            c.store_id === storeId
              ? { ...c, items: c.items.filter((i) => i.product_id !== productId) }
              : c
          )
          .filter((c) => c.items.length > 0)
      );
      if (!itemId) return;
      try {
        await remoteCart.removeItem(token!, itemId);
        await refreshRemote();
      } catch (err) {
        setCarts(previous);
        throw err;
      }
    },
    [carts, isCustomer, token, refreshRemote]
  );

  const updateQty = useCallback(
    async (storeId: number, productId: number, qty: number) => {
      if (qty <= 0) {
        await removeItem(storeId, productId);
        return;
      }
      if (!isCustomer) {
        setCarts(localCart.updateQuantity(storeId, productId, qty));
        return;
      }
      const previous = carts;
      const itemId = findRemoteItemId(carts, storeId, productId);
      setCarts((prev) =>
        prev.map((c) =>
          c.store_id === storeId
            ? {
                ...c,
                items: c.items.map((i) =>
                  i.product_id === productId ? { ...i, quantity: qty } : i
                ),
              }
            : c
        )
      );
      if (!itemId) return;
      try {
        await remoteCart.updateItemQty(token!, itemId, qty);
        await refreshRemote();
      } catch (err) {
        setCarts(previous);
        throw err;
      }
    },
    [carts, isCustomer, token, refreshRemote, removeItem]
  );

  const clearStoreCart = useCallback(
    async (storeId: number) => {
      if (!isCustomer) {
        setCarts(localCart.clearCart(storeId));
        return;
      }
      const previous = carts;
      setCarts((prev) => prev.filter((c) => c.store_id !== storeId));
      try {
        await remoteCart.clearStoreCart(token!, storeId);
        await refreshRemote();
      } catch (err) {
        setCarts(previous);
        throw err;
      }
    },
    [carts, isCustomer, token, refreshRemote]
  );

  const cartCount = useMemo(() => getCartCount(carts), [carts]);
  const grandTotal = useMemo(() => getGrandTotal(carts), [carts]);

  const value: CartContextValue = {
    carts,
    cartCount,
    loading,
    addItem,
    removeItem,
    updateQty,
    clearStoreCart,
    getTotal: getCartTotal,
    grandTotal,
  };

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): CartContextValue {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used inside a CartProvider");
  return ctx;
}
```

- [ ] **Step 3: Update consumers that called `addItem`/`removeItem` synchronously**

Existing UI does not `await`. That is fine — fire-and-forget is OK with optimistic updates. If any consumer needs to react to errors, wrap in `try/catch` with a toast.

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```

- [ ] **Step 5: Manual verification**

```bash
cd frontend && npm run dev
```

In the browser:
1. As guest: add items to cart → confirm `kb_carts` in localStorage.
2. Log in as customer → confirm cart syncs to backend (Network tab shows `POST /api/v1/carts/sync`), localStorage cleared, cart still visible.
3. Add another item while logged in → confirm `POST /api/v1/carts/items`.
4. Update qty → confirm `PATCH /api/v1/carts/items/{id}`.
5. Open new browser/incognito, log in as same user → confirm cart loads from backend.
6. Log out → confirm cart resets to empty (or whatever localStorage held before login, depending on flow).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/CartContext.tsx
git commit -m "feat(cart): auth-aware backend with sync on login and optimistic updates"
```

---

## Task 7: OrderStatusBadge component

**Files:**
- Create: `frontend/src/components/orders/OrderStatusBadge.tsx`
- Create: `frontend/src/components/orders/OrderStatusBadge.module.css`

- [ ] **Step 1: Component file**

Create `frontend/src/components/orders/OrderStatusBadge.tsx`:

```tsx
import type { OrderStatus } from "@/types";
import styles from "./OrderStatusBadge.module.css";

const LABELS: Record<OrderStatus, string> = {
  pending: "Pending",
  packed: "Packed",
  dispatched: "Dispatched",
  delivered: "Delivered",
  cancelled: "Cancelled",
};

export default function OrderStatusBadge({ status }: { status: OrderStatus }) {
  return <span className={`${styles.badge} ${styles[status]}`}>{LABELS[status]}</span>;
}
```

- [ ] **Step 2: Styles**

Create `frontend/src/components/orders/OrderStatusBadge.module.css`:

```css
.badge {
  display: inline-block;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.pending { background: #fef3c7; color: #92400e; }
.packed { background: #dbeafe; color: #1e40af; }
.dispatched { background: #ede9fe; color: #5b21b6; }
.delivered { background: #dcfce7; color: #166534; }
.cancelled { background: #fee2e2; color: #991b1b; }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/orders/OrderStatusBadge.tsx frontend/src/components/orders/OrderStatusBadge.module.css
git commit -m "feat(orders): add OrderStatusBadge"
```

---

## Task 8: OrderTimeline component

**Files:**
- Create: `frontend/src/components/orders/OrderTimeline.tsx`
- Create: `frontend/src/components/orders/OrderTimeline.module.css`

- [ ] **Step 1: Component**

Create `frontend/src/components/orders/OrderTimeline.tsx`:

```tsx
import type { OrderStatus } from "@/types";
import styles from "./OrderTimeline.module.css";

const STEPS: { key: OrderStatus; label: string }[] = [
  { key: "pending", label: "Order placed" },
  { key: "packed", label: "Packed" },
  { key: "dispatched", label: "Dispatched" },
  { key: "delivered", label: "Delivered" },
];

const ORDER_INDEX: Record<OrderStatus, number> = {
  pending: 0,
  packed: 1,
  dispatched: 2,
  delivered: 3,
  cancelled: -1,
};

export default function OrderTimeline({ status }: { status: OrderStatus }) {
  if (status === "cancelled") {
    return <div className={styles.cancelled}>Order cancelled</div>;
  }
  const current = ORDER_INDEX[status];
  return (
    <ol className={styles.timeline}>
      {STEPS.map((step, idx) => {
        const completed = idx <= current;
        return (
          <li
            key={step.key}
            className={`${styles.step} ${completed ? styles.completed : ""}`}
          >
            <span className={styles.dot} />
            <span className={styles.label}>{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}
```

- [ ] **Step 2: Styles**

Create `frontend/src/components/orders/OrderTimeline.module.css`:

```css
.timeline {
  display: flex;
  gap: 1rem;
  list-style: none;
  margin: 0;
  padding: 0;
}
.step { display: flex; flex-direction: column; align-items: center; gap: 0.4rem; flex: 1; }
.dot {
  width: 14px; height: 14px; border-radius: 50%;
  background: var(--color-border, #d1d5db);
}
.completed .dot { background: var(--color-primary, #16a34a); }
.label { font-size: 0.85rem; color: var(--color-text-muted, #4b5563); text-align: center; }
.completed .label { color: var(--color-text, #111827); font-weight: 600; }
.cancelled {
  color: #991b1b; font-weight: 600; padding: 0.5rem 0;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/orders/OrderTimeline.tsx frontend/src/components/orders/OrderTimeline.module.css
git commit -m "feat(orders): add OrderTimeline"
```

---

## Task 9: OrderItemList component

**Files:**
- Create: `frontend/src/components/orders/OrderItemList.tsx`
- Create: `frontend/src/components/orders/OrderItemList.module.css`

- [ ] **Step 1: Component**

```tsx
import type { OrderItem } from "@/types";
import styles from "./OrderItemList.module.css";

export default function OrderItemList({ items }: { items: OrderItem[] }) {
  return (
    <ul className={styles.list}>
      {items.map((item) => (
        <li key={item.id} className={styles.row}>
          <span className={styles.name}>{item.product_name_snapshot}</span>
          <span className={styles.qty}>× {item.quantity}</span>
          <span className={styles.unit}>₹{item.unit_price_snapshot.toFixed(2)}</span>
          <span className={styles.total}>₹{item.line_total.toFixed(2)}</span>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 2: Styles**

```css
.list { list-style: none; margin: 0; padding: 0; }
.row {
  display: grid;
  grid-template-columns: 1fr auto auto auto;
  gap: 1rem;
  padding: 0.6rem 0;
  border-bottom: 1px solid var(--color-border, #e5e7eb);
}
.name { font-weight: 500; }
.qty, .unit { color: var(--color-text-muted, #6b7280); font-variant-numeric: tabular-nums; }
.total { font-weight: 600; font-variant-numeric: tabular-nums; }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/orders/OrderItemList.tsx frontend/src/components/orders/OrderItemList.module.css
git commit -m "feat(orders): add OrderItemList"
```

---

## Task 10: OrderActionButtons component

**Files:**
- Create: `frontend/src/components/orders/OrderActionButtons.tsx`
- Create: `frontend/src/components/orders/OrderActionButtons.module.css`

- [ ] **Step 1: Component**

Create `frontend/src/components/orders/OrderActionButtons.tsx`:

```tsx
"use client";

import { useState } from "react";
import { cancelOrder, transitionOrder } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import type { Order, OrderStatus, UserRole } from "@/types";
import styles from "./OrderActionButtons.module.css";

const NEXT_TRANSITION: Partial<Record<OrderStatus, "packed" | "dispatched" | "delivered">> = {
  pending: "packed",
  packed: "dispatched",
  dispatched: "delivered",
};

const NEXT_LABEL: Record<NonNullable<typeof NEXT_TRANSITION[OrderStatus]>, string> = {
  packed: "Mark Packed",
  dispatched: "Mark Dispatched",
  delivered: "Mark Delivered",
};

interface Props {
  order: Order;
  role: UserRole;
  onChange: (next: Order) => void;
}

export default function OrderActionButtons({ order, role, onChange }: Props) {
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canTransition = role !== "customer" && NEXT_TRANSITION[order.status] !== undefined;
  const canCancelCustomer = role === "customer" && order.status === "pending";
  const canCancelStaff =
    role !== "customer" && order.status !== "delivered" && order.status !== "cancelled";

  const handleTransition = async () => {
    if (!token) return;
    const target = NEXT_TRANSITION[order.status]!;
    if (target === "delivered" && !confirm("Cash collected from customer?")) return;
    setBusy(true);
    setError(null);
    try {
      const next = await transitionOrder(token, order.id, target);
      onChange(next);
    } catch (e) {
      setError((e as { detail?: string })?.detail ?? "Could not update order.");
    } finally {
      setBusy(false);
    }
  };

  const handleCancel = async () => {
    if (!token) return;
    if (!confirm("Cancel this order? Stock will be restored.")) return;
    setBusy(true);
    setError(null);
    try {
      const next = await cancelOrder(token, order.id);
      onChange(next);
    } catch (e) {
      setError((e as { detail?: string })?.detail ?? "Could not cancel order.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={styles.actions}>
      {canTransition && (
        <button onClick={handleTransition} disabled={busy} className={styles.primary}>
          {NEXT_LABEL[NEXT_TRANSITION[order.status]!]}
        </button>
      )}
      {(canCancelCustomer || canCancelStaff) && (
        <button onClick={handleCancel} disabled={busy} className={styles.danger}>
          Cancel order
        </button>
      )}
      {error && <span className={styles.error}>{error}</span>}
    </div>
  );
}
```

- [ ] **Step 2: Styles**

```css
.actions { display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; }
.primary {
  background: var(--color-primary, #16a34a); color: white;
  padding: 0.5rem 1rem; border-radius: 6px; border: none; cursor: pointer; font-weight: 600;
}
.primary:disabled { opacity: 0.6; cursor: progress; }
.danger {
  background: transparent; color: #991b1b; border: 1px solid #fca5a5;
  padding: 0.5rem 1rem; border-radius: 6px; cursor: pointer; font-weight: 600;
}
.error { color: #991b1b; font-size: 0.85rem; }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/orders/OrderActionButtons.tsx frontend/src/components/orders/OrderActionButtons.module.css
git commit -m "feat(orders): add OrderActionButtons"
```

---

## Task 11: OrderCard component

**Files:**
- Create: `frontend/src/components/orders/OrderCard.tsx`
- Create: `frontend/src/components/orders/OrderCard.module.css`

- [ ] **Step 1: Component**

```tsx
import Link from "next/link";
import OrderStatusBadge from "./OrderStatusBadge";
import type { Order, UserRole } from "@/types";
import styles from "./OrderCard.module.css";

interface Props {
  order: Order;
  role: UserRole;
}

const HREF_BY_ROLE: Record<UserRole, (id: number) => string> = {
  customer: (id) => `/account/orders/${id}`,
  seller: (id) => `/seller/orders/${id}`,
  admin: (id) => `/admin/orders/${id}`,
};

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const diffSec = Math.round((Date.now() - then) / 1000);
  if (diffSec < 60) return `${diffSec}s ago`;
  const min = Math.round(diffSec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.round(hr / 24)}d ago`;
}

export default function OrderCard({ order, role }: Props) {
  const href = HREF_BY_ROLE[role](order.id);
  return (
    <Link href={href} className={styles.card}>
      <div className={styles.header}>
        <span className={styles.id}>#{order.id}</span>
        <OrderStatusBadge status={order.status} />
      </div>
      <div className={styles.title}>{order.store_name}</div>
      {order.customer_name && (
        <div className={styles.subtitle}>For {order.customer_name}</div>
      )}
      <div className={styles.meta}>
        <span className={styles.total}>₹{order.total.toFixed(2)}</span>
        <span className={styles.time}>{relativeTime(order.placed_at)}</span>
      </div>
    </Link>
  );
}
```

- [ ] **Step 2: Styles**

```css
.card {
  display: block;
  padding: 1rem;
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 10px;
  text-decoration: none;
  color: inherit;
  background: var(--color-surface, #fff);
  transition: border-color 120ms;
}
.card:hover { border-color: var(--color-primary, #16a34a); }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem; }
.id { font-size: 0.85rem; color: var(--color-text-muted, #6b7280); }
.title { font-weight: 600; font-size: 1.05rem; }
.subtitle { font-size: 0.85rem; color: var(--color-text-muted, #6b7280); margin-top: 0.15rem; }
.meta {
  display: flex; justify-content: space-between; align-items: baseline;
  margin-top: 0.5rem; font-variant-numeric: tabular-nums;
}
.total { font-weight: 700; font-size: 1.1rem; }
.time { font-size: 0.8rem; color: var(--color-text-muted, #6b7280); }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/orders/OrderCard.tsx frontend/src/components/orders/OrderCard.module.css
git commit -m "feat(orders): add OrderCard"
```

---

## Task 12: ActiveOrdersWidget (polling)

**Files:**
- Create: `frontend/src/components/orders/ActiveOrdersWidget.tsx`
- Create: `frontend/src/components/orders/ActiveOrdersWidget.module.css`

- [ ] **Step 1: Component**

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listOrders } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import OrderCard from "./OrderCard";
import type { Order, UserRole } from "@/types";
import styles from "./ActiveOrdersWidget.module.css";

interface Props {
  role: UserRole;
  limit?: number;
}

const VIEW_ALL_HREF: Record<UserRole, string> = {
  customer: "/account/orders",
  seller: "/seller/orders",
  admin: "/admin/orders",
};

const POLL_MS = 15_000;

export default function ActiveOrdersWidget({ role, limit = 5 }: Props) {
  const { token } = useAuth();
  const [orders, setOrders] = useState<Order[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    const tick = () =>
      listOrders(token, "active")
        .then((data) => {
          if (!cancelled) {
            setOrders(data.slice(0, limit));
            setError(null);
          }
        })
        .catch((e: { detail?: string }) => {
          if (!cancelled) setError(e?.detail ?? "Could not load orders.");
        });
    tick();
    const id = setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [token, limit]);

  return (
    <section className={styles.widget}>
      <div className={styles.header}>
        <h2 className={styles.title}>Active orders</h2>
        <Link href={VIEW_ALL_HREF[role]} className={styles.viewAll}>
          View all
        </Link>
      </div>
      {error && <div className={styles.error}>{error}</div>}
      {orders.length === 0 ? (
        <div className={styles.empty}>No active orders.</div>
      ) : (
        <div className={styles.grid}>
          {orders.map((o) => (
            <OrderCard key={o.id} order={o} role={role} />
          ))}
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Styles**

```css
.widget { margin: 1.5rem 0; }
.header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 0.8rem; }
.title { font-size: 1.2rem; margin: 0; }
.viewAll { color: var(--color-primary, #16a34a); font-weight: 600; text-decoration: none; }
.empty { color: var(--color-text-muted, #6b7280); padding: 1rem; border: 1px dashed var(--color-border, #e5e7eb); border-radius: 8px; }
.error { color: #991b1b; font-size: 0.9rem; margin-bottom: 0.5rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 0.8rem; }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/orders/ActiveOrdersWidget.tsx frontend/src/components/orders/ActiveOrdersWidget.module.css
git commit -m "feat(orders): add ActiveOrdersWidget with 15s polling"
```

---

## Task 13: AddressPicker component

**Files:**
- Create: `frontend/src/components/orders/AddressPicker.tsx`
- Create: `frontend/src/components/orders/AddressPicker.module.css`

- [ ] **Step 1: Component**

```tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import styles from "./AddressPicker.module.css";

interface CustomerAddressApi {
  id: number;
  label: string | null;
  is_default: boolean;
  // Backend AddressPayload uses flat snake_case fields — see
  // backend/app/src/app/schemas/address.py.
  address: {
    address_line1: string;
    address_line2?: string | null;
    city: string;
    state: string;
    pincode: string;
  };
}

interface CustomerProfileResponse {
  // Permissive — the real response also has user_id, email, first_name, etc.
  // We only need addresses here.
  addresses: CustomerAddressApi[];
}

interface Props {
  value: number | null;
  onChange: (id: number) => void;
}

export default function AddressPicker({ value, onChange }: Props) {
  const { token } = useAuth();
  const [addresses, setAddresses] = useState<CustomerAddressApi[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    get<CustomerProfileResponse>("/api/v1/customers/me", token)
      .then((data) => {
        setAddresses(data.addresses);
        if (value === null && data.addresses.length > 0) {
          const def = data.addresses.find((a) => a.is_default) ?? data.addresses[0];
          onChange(def.id);
        }
      })
      .finally(() => setLoading(false));
  }, [token, value, onChange]);

  if (loading) return <div className={styles.loading}>Loading addresses…</div>;
  if (addresses.length === 0) {
    return (
      <div className={styles.empty}>
        No saved address.{" "}
        <Link href="/account/settings" className={styles.link}>Add one</Link>
      </div>
    );
  }

  return (
    <div className={styles.picker}>
      <label htmlFor="address-picker" className={styles.label}>Deliver to</label>
      <select
        id="address-picker"
        value={value ?? ""}
        onChange={(e) => onChange(Number(e.target.value))}
        className={styles.select}
      >
        {addresses.map((a) => (
          <option key={a.id} value={a.id}>
            {(a.label ?? "Address")} — {a.address.address_line1}, {a.address.city} {a.address.pincode}
          </option>
        ))}
      </select>
    </div>
  );
}
```

- [ ] **Step 2: Styles**

```css
.picker { display: flex; flex-direction: column; gap: 0.3rem; }
.label { font-size: 0.85rem; color: var(--color-text-muted, #6b7280); }
.select { padding: 0.5rem; border-radius: 6px; border: 1px solid var(--color-border, #d1d5db); }
.loading { color: var(--color-text-muted, #6b7280); }
.empty { color: var(--color-text-muted, #6b7280); }
.link { color: var(--color-primary, #16a34a); font-weight: 600; }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/orders/AddressPicker.tsx frontend/src/components/orders/AddressPicker.module.css
git commit -m "feat(orders): add AddressPicker"
```

---

## Task 14: Wire checkout into /cart page

**Files:**
- Modify: `frontend/src/app/cart/page.tsx`
- Modify: `frontend/src/app/cart/page.module.css` (only if new classes needed)

- [ ] **Step 1: Replace the disabled checkout block with a smart one**

Modify `frontend/src/app/cart/page.tsx`. Replace the bottom `totalBar`/`checkoutBtn` block with:

```tsx
"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/AuthContext";
import { useCart } from "@/lib/CartContext";
import { placeOrder } from "@/lib/orders";
import AddressPicker from "@/components/orders/AddressPicker";
import styles from "./page.module.css";

// ... keep existing imports + empty-state ...

export default function CartPage() {
  const { carts, removeItem, updateQty, clearStoreCart, getTotal, grandTotal } = useCart();
  const { dbUser, token } = useAuth();
  const router = useRouter();
  const [addressId, setAddressId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ... existing empty-state branch ...

  const isCustomer = dbUser?.role === "customer";

  const onCheckout = async () => {
    if (!token || !addressId) return;
    setSubmitting(true);
    setError(null);
    try {
      const orders = await placeOrder(token, addressId);
      router.push(`/account/orders?placed=${orders.length}`);
    } catch (e) {
      const detail = (e as { detail?: unknown })?.detail;
      setError(typeof detail === "string" ? detail : "Could not place order.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.pageInner}>
        {/* ... existing header + per-store cart groups ... */}

        {isCustomer && (
          <div className={styles.addressBlock}>
            <AddressPicker value={addressId} onChange={setAddressId} />
          </div>
        )}

        <div className={styles.totalBar}>
          <span className={styles.totalLabel}>Grand Total</span>
          <div className={styles.totalRight}>
            <span className={styles.totalValue}>₹{grandTotal}</span>
            {!dbUser ? (
              <Link href="/login?next=/cart" className={styles.checkoutBtn}>
                Login to checkout
              </Link>
            ) : !isCustomer ? (
              <span className={styles.checkoutBtn} aria-disabled>
                Customer login required
              </span>
            ) : addressId === null ? (
              <Link href="/account/settings" className={styles.checkoutBtn}>
                Add address to checkout
              </Link>
            ) : (
              <button
                className={styles.checkoutBtn}
                onClick={onCheckout}
                disabled={submitting}
              >
                {submitting ? "Placing order…" : "Place Order"}
              </button>
            )}
          </div>
        </div>
        {error && <div className={styles.error}>{error}</div>}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add `.addressBlock` and `.error` to `cart/page.module.css`**

```css
.addressBlock { margin: 1rem 0; padding: 1rem; border: 1px solid var(--color-border, #e5e7eb); border-radius: 10px; }
.error { color: #991b1b; margin-top: 0.6rem; font-size: 0.9rem; }
```

- [ ] **Step 3: Manual test**

```bash
cd frontend && npm run dev
```

Steps:
1. Guest with cart → visit `/cart` → button reads "Login to checkout" → click → redirects to login.
2. Login as customer with no address → `/cart` button reads "Add address to checkout".
3. Add a customer address via `/account/settings`, return to `/cart` → button enabled.
4. Click "Place Order" → expect redirect to `/account/orders?placed=N`.
5. Trigger error: temporarily reduce `StoreInventory.stock` below cart qty in DB; click again → expect inline error message.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/cart/page.tsx frontend/src/app/cart/page.module.css
git commit -m "feat(cart): enable checkout with address picker"
```

---

## Task 15: Customer order list + detail pages

**Files:**
- Create: `frontend/src/app/account/orders/page.tsx`
- Create: `frontend/src/app/account/orders/page.module.css`
- Create: `frontend/src/app/account/orders/[id]/page.tsx`
- Create: `frontend/src/app/account/orders/[id]/page.module.css`

- [ ] **Step 1: List page**

Create `frontend/src/app/account/orders/page.tsx`:

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { listOrders } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import OrderCard from "@/components/orders/OrderCard";
import type { Order } from "@/types";
import styles from "./page.module.css";

type Tab = "active" | "history";

export default function CustomerOrdersPage() {
  const { token } = useAuth();
  const [tab, setTab] = useState<Tab>("active");
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const search = useSearchParams();
  const justPlaced = search.get("placed");

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    listOrders(token, tab)
      .then(setOrders)
      .finally(() => setLoading(false));
  }, [token, tab]);

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Your orders</h1>
      {justPlaced && (
        <div className={styles.toast}>
          {justPlaced} order{Number(justPlaced) > 1 ? "s" : ""} placed successfully.
        </div>
      )}
      <div className={styles.tabs}>
        <button
          className={tab === "active" ? styles.tabActive : styles.tab}
          onClick={() => setTab("active")}
        >Active</button>
        <button
          className={tab === "history" ? styles.tabActive : styles.tab}
          onClick={() => setTab("history")}
        >History</button>
      </div>
      {loading ? (
        <div className={styles.empty}>Loading…</div>
      ) : orders.length === 0 ? (
        <div className={styles.empty}>No {tab} orders.</div>
      ) : (
        <div className={styles.grid}>
          {orders.map((o) => (
            <OrderCard key={o.id} order={o} role="customer" />
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: List page styles**

Create `frontend/src/app/account/orders/page.module.css`:

```css
.page { padding: 1.5rem; max-width: 1100px; margin: 0 auto; }
.title { font-size: 1.6rem; margin-bottom: 1rem; }
.toast { background: #dcfce7; color: #166534; padding: 0.6rem 1rem; border-radius: 8px; margin-bottom: 1rem; }
.tabs { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
.tab, .tabActive {
  border: 1px solid var(--color-border, #d1d5db);
  background: transparent;
  padding: 0.5rem 1rem;
  border-radius: 999px;
  cursor: pointer;
  font-weight: 500;
}
.tabActive { background: var(--color-primary, #16a34a); color: white; border-color: transparent; }
.empty { color: var(--color-text-muted, #6b7280); padding: 2rem; text-align: center; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; }
```

- [ ] **Step 3: Detail page**

Create `frontend/src/app/account/orders/[id]/page.tsx`:

```tsx
"use client";

import { use, useEffect, useState } from "react";
import { getOrder } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import OrderTimeline from "@/components/orders/OrderTimeline";
import OrderItemList from "@/components/orders/OrderItemList";
import OrderActionButtons from "@/components/orders/OrderActionButtons";
import OrderStatusBadge from "@/components/orders/OrderStatusBadge";
import type { Order } from "@/types";
import styles from "./page.module.css";

export default function CustomerOrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { token } = useAuth();
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    getOrder(token, Number(id))
      .then(setOrder)
      .catch((e: { detail?: string }) => setError(e?.detail ?? "Could not load order."));
  }, [token, id]);

  if (error) return <div className={styles.error}>{error}</div>;
  if (!order) return <div className={styles.loading}>Loading…</div>;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Order #{order.id}</h1>
        <OrderStatusBadge status={order.status} />
      </div>
      <p className={styles.subtitle}>{order.store_name}</p>

      <section className={styles.section}>
        <OrderTimeline status={order.status} />
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Items</h2>
        <OrderItemList items={order.items} />
        <div className={styles.totals}>
          <div><span>Subtotal</span><span>₹{order.subtotal.toFixed(2)}</span></div>
          <div><span>Delivery</span><span>₹{order.delivery_fee.toFixed(2)}</span></div>
          <div><span>Tax</span><span>₹{order.tax.toFixed(2)}</span></div>
          <div className={styles.grand}><span>Total</span><span>₹{order.total.toFixed(2)}</span></div>
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Payment</h2>
        <p>{order.payment.method.toUpperCase()} · {order.payment.status}</p>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Delivery to</h2>
        <p>{order.delivery_address_snapshot}</p>
      </section>

      <section className={styles.section}>
        <OrderActionButtons order={order} role="customer" onChange={setOrder} />
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Detail page styles**

```css
.page { padding: 1.5rem; max-width: 800px; margin: 0 auto; }
.header { display: flex; justify-content: space-between; align-items: baseline; }
.title { font-size: 1.6rem; margin: 0; }
.subtitle { color: var(--color-text-muted, #6b7280); margin-top: 0.25rem; }
.section { margin-top: 1.5rem; padding: 1rem; background: var(--color-surface, #fff); border: 1px solid var(--color-border, #e5e7eb); border-radius: 10px; }
.sectionTitle { font-size: 1.05rem; margin: 0 0 0.6rem; }
.totals { display: flex; flex-direction: column; gap: 0.3rem; margin-top: 0.8rem; font-variant-numeric: tabular-nums; }
.totals div { display: flex; justify-content: space-between; }
.grand { font-weight: 700; font-size: 1.1rem; border-top: 1px solid var(--color-border, #e5e7eb); padding-top: 0.4rem; margin-top: 0.3rem; }
.loading, .error { padding: 2rem; text-align: center; color: var(--color-text-muted, #6b7280); }
.error { color: #991b1b; }
```

- [ ] **Step 5: Manual smoke**

Place an order, navigate to `/account/orders` → see card → click → see detail page → confirm "Cancel order" appears (status is Pending) → cancel → confirm Cancelled timeline copy + status badge.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/account/orders
git commit -m "feat(orders): add customer order list and detail pages"
```

---

## Task 16: Add Active Orders widget + nav link to customer dashboard

**Files:**
- Modify: `frontend/src/app/account/page.tsx`
- Modify: `frontend/src/app/account/layout.tsx`

- [ ] **Step 1: Add nav entry to customer layout**

Find `CUSTOMER_NAV` in `frontend/src/app/account/layout.tsx` and add an Orders entry:

```tsx
const CUSTOMER_NAV = [
  { href: "/account/orders", label: "Orders", icon: "📦" },
  { href: "/account/settings", label: "Settings", icon: "⚙️" },
];
```

- [ ] **Step 2: Mount widget on `/account`**

Open `frontend/src/app/account/page.tsx`. If the page is currently a redirect, change it to render the widget; otherwise add `<ActiveOrdersWidget role="customer" />` near the top:

```tsx
"use client";
import ActiveOrdersWidget from "@/components/orders/ActiveOrdersWidget";

export default function AccountHomePage() {
  return (
    <div style={{ padding: "1.5rem", maxWidth: 1100, margin: "0 auto" }}>
      <h1>My account</h1>
      <ActiveOrdersWidget role="customer" limit={5} />
    </div>
  );
}
```

(If the redirect must stay, add a new `/account/dashboard` route instead and adjust the redirect target — read the file first.)

- [ ] **Step 3: Manual smoke**

`/account` shows the widget. Place an order in another tab → within 15s the widget reflects it without a refresh.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/account/layout.tsx frontend/src/app/account/page.tsx
git commit -m "feat(account): add orders nav link and active orders widget"
```

---

## Task 17: Seller order list + detail pages + dashboard widget

**Files:**
- Create: `frontend/src/app/seller/orders/page.tsx`
- Create: `frontend/src/app/seller/orders/page.module.css`
- Create: `frontend/src/app/seller/orders/[id]/page.tsx`
- Create: `frontend/src/app/seller/orders/[id]/page.module.css`
- Modify: `frontend/src/app/seller/layout.tsx`
- Modify: `frontend/src/app/seller/page.tsx`

- [ ] **Step 1: Add Orders nav entry**

Find the seller nav definition (likely in `seller/layout.tsx`) and add:

```tsx
{ href: "/seller/orders", label: "Orders", icon: "📦" },
```

Place it above "Inventory" so it is the most prominent action.

- [ ] **Step 2: Mount widget on `/seller`**

Open `frontend/src/app/seller/page.tsx` and add `<ActiveOrdersWidget role="seller" limit={10} />` as the primary section.

- [ ] **Step 3: List page**

Create `frontend/src/app/seller/orders/page.tsx` — same shape as the customer list (Task 15) but with `role="seller"` passed to `OrderCard` and the page title "Store orders". Tabs Active / History.

- [ ] **Step 4: Detail page**

Create `frontend/src/app/seller/orders/[id]/page.tsx` — same shape as the customer detail (Task 15) but `role="seller"`. The shared `OrderActionButtons` automatically renders the next-transition + cancel buttons because the role check inside it gates customer vs staff behavior.

- [ ] **Step 5: Manual smoke**

Log in as the seller for the store that received the order placed in Task 15. Visit `/seller`. Confirm widget shows the new order. Click in → press "Mark Packed" → status updates and timeline advances. Repeat to Dispatched, then Delivered (confirm cash dialog). After Delivered, payment row in DB shows status=Paid + paid_at.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/seller
git commit -m "feat(seller): add orders pages, widget, and nav link"
```

---

## Task 18: Admin order list + detail + widget + nav

**Files:**
- Create: `frontend/src/app/admin/orders/page.tsx` + `.module.css`
- Create: `frontend/src/app/admin/orders/[id]/page.tsx` + `.module.css`
- Modify: `frontend/src/app/admin/layout.tsx` (add nav entry)
- Modify: `frontend/src/app/admin/page.tsx` (mount widget)

- [ ] **Step 1: Nav entry**

Add `{ href: "/admin/orders", label: "Orders", icon: "📦" }` to the admin nav array.

- [ ] **Step 2: Mount widget on `/admin`**

Add `<ActiveOrdersWidget role="admin" limit={10} />` near the top of the admin landing.

- [ ] **Step 3: List page**

Create `frontend/src/app/admin/orders/page.tsx` mirroring the seller list (Task 17), `role="admin"`, page title "All orders". Optional simple filter dropdown for store_id (single `<select>` populated from the admin's existing data; can be omitted in MVP and added later).

- [ ] **Step 4: Detail page**

Create `frontend/src/app/admin/orders/[id]/page.tsx` mirroring the customer detail. Pass `role="admin"` to `OrderActionButtons`. Per the role logic inside the component, admin sees only the "Cancel order" button (no transitions).

To enforce this in the component, confirm `OrderActionButtons` already gates transitions to non-customer roles (it does — `canTransition = role !== "customer" && ...`). Adjust the gate so admin doesn't get transition buttons:

```tsx
const canTransition = role === "seller" && NEXT_TRANSITION[order.status] !== undefined;
```

- [ ] **Step 5: Update `OrderActionButtons` per Step 4**

Modify `frontend/src/components/orders/OrderActionButtons.tsx`, change the `canTransition` line to:

```tsx
const canTransition = role === "seller" && NEXT_TRANSITION[order.status] !== undefined;
```

- [ ] **Step 6: Manual smoke**

Log in as admin → `/admin` → widget shows all platform orders → click → detail page → "Cancel order" visible, no transition buttons → cancel → confirm restock + customer email triggered.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/admin frontend/src/components/orders/OrderActionButtons.tsx
git commit -m "feat(admin): add orders pages, widget, nav, and admin-only cancel control"
```

---

## Task 19: Navbar "Orders" link for logged-in customers

**Files:**
- Modify: `frontend/src/components/Navbar.tsx`

- [ ] **Step 1: Add link**

Find the section that renders auth-aware links. Add an "Orders" link next to the existing customer nav entries, conditional on `dbUser?.role === "customer"`:

```tsx
{dbUser?.role === "customer" && (
  <Link href="/account/orders" className={styles.navLink}>Orders</Link>
)}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Navbar.tsx
git commit -m "feat(navbar): add Orders link for customers"
```

---

## Task 20: Final manual verification

**Files:** none (verification only)

- [ ] **Step 1: Lint and type-check**

```bash
cd frontend && npm run lint && npx tsc --noEmit && npm run build
```

Expected: clean across all three.

- [ ] **Step 2: End-to-end manual checklist**

Run backend (`cd backend/app && uv run uvicorn app.main:app --reload`), Celery worker (`uv run celery -A app.core.celery_app worker --loglevel=info`), Redis + Postgres via `docker-compose up -d`, and frontend (`cd frontend && npm run dev`).

Run through this list, taking notes if anything fails:

- [ ] Guest add to cart works.
- [ ] Login as customer triggers cart sync; localStorage cleared.
- [ ] Cart edits while logged in update DB and survive a hard refresh.
- [ ] Cart loads from DB in a fresh browser/incognito after login.
- [ ] Optimistic update rollback: simulate API failure (stop backend), update qty, observe UI revert + error toast.
- [ ] `/cart` checkout button disabled / labelled correctly across guest, no-address, and ready states.
- [ ] Place order with multi-store cart fans out into N orders → redirect to `/account/orders?placed=N` → success banner.
- [ ] Customer order list shows Active and History tabs; each card links to detail; detail shows timeline + items + payment + address.
- [ ] Customer can cancel only Pending; cancel restores stock (verify in DB or by re-listing inventory).
- [ ] Seller `/seller` widget shows the new order within 15s; detail page shows transition buttons.
- [ ] Seller marks Packed → Dispatched → Delivered (confirm dialog appears for Delivered); after Delivered, customer detail shows Payment status = Paid.
- [ ] Seller can cancel pre-Delivered.
- [ ] Other seller cannot view or transition this seller's orders (403 in Network tab).
- [ ] Admin `/admin` widget shows all platform orders; detail page exposes only Cancel.
- [ ] Admin cancel of a Dispatched order works and triggers restock.
- [ ] Email logs visible in Celery worker output for placed/transition/cancel events.

- [ ] **Step 3: Push branch and open PR**

(Wait for explicit user approval first.)

```bash
git push -u origin <branch>
gh pr create --title "feat(orders): frontend cart sync, checkout, dashboards, and order pages" --body "$(cat <<'EOF'
## Summary
- DB-backed cart for logged-in customers with optimistic updates and rollback on failure; localStorage retained for guests.
- Sync of localStorage carts to backend on login; carts now follow the user across devices.
- Cart page checkout enabled with address picker; multi-store cart fans out to N orders via single tap.
- New customer / seller / admin order list and detail pages, plus an `<ActiveOrdersWidget />` mounted on each role's dashboard with 15-second polling.
- Shared role-aware components (`OrderCard`, `OrderTimeline`, `OrderActionButtons`, `OrderItemList`, `OrderStatusBadge`).
- Navigation links added to navbar (customer) and dashboard sidebars (seller, admin).

Depends on the backend orders PR being merged first.

## Test plan
- [ ] `npm run lint`, `npx tsc --noEmit`, `npm run build` all clean.
- [ ] Manual checklist in `docs/superpowers/plans/2026-05-02-orders-frontend.md` Task 20 completed.

## Migration / env-var notes
- None for the frontend. Backend migration ships in the backend PR.
EOF
)"
```

---

## Self-Review Checklist (run after writing all tasks above)

- [ ] Spec coverage: cart DB-backed for logged-in users ✓, sync on login ✓, optimistic UI ✓, multi-store fan-out checkout ✓, address picker ✓, role-aware order list + detail for all three roles ✓, dashboard widgets ✓, polling ✓, status transitions + cancel flows ✓, navigation entries ✓.
- [ ] No "TBD" or "implement later" placeholders. The one place tasks reference an externally-named file (the seller layout's nav definition) explicitly says to read the file and locate the existing array.
- [ ] Type/component names consistent: `OrderActionButtons`, `OrderCard`, `OrderTimeline`, `OrderItemList`, `OrderStatusBadge`, `ActiveOrdersWidget`, `AddressPicker`, `placeOrder`, `transitionOrder`, `cancelOrder`, `listOrders`, `getOrder`, `syncCarts`, `listCarts`.
- [ ] `OrderActionButtons` role gating finalized in Task 18 (`canTransition = role === "seller"`).
- [ ] Customer cart `inventory_id` propagation handled at types (Task 1) → adapters (Task 3, 4) → call sites (Task 5) → context (Task 6).
