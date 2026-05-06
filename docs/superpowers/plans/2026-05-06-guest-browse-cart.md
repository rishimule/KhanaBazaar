# Guest Browse + Cart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow unauthenticated visitors to browse stores, add items to a per-store cart, and only require login at checkout. Guest cart merges into the customer's server-side cart on login (already wired; this plan removes the redirect blockers and surfaces drop notifications).

**Architecture:** Frontend-only changes. Drop login redirects on store list and store detail pages — backend catalog and store reads are already public. Honor `?next=` query parameter on the login page so users return to checkout post-OTP. Surface dropped items from `POST /api/v1/carts/sync` via a small banner component injected into the customer layout.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript 5, `next-intl` for i18n, CSS Modules. No frontend tests configured — verification is manual against the running dev server.

**Spec:** `docs/superpowers/specs/2026-05-06-guest-browse-cart-design.md`

**Branch:** `feat/guest-browse-cart` (already created, spec already committed)

---

## Pre-flight

Before starting, confirm the dev stack runs cleanly. From the repo root:

```bash
docker-compose up -d
cd backend/app && uv sync && uv run alembic upgrade head
cd ../../frontend && npm install
```

Run frontend in one terminal:

```bash
cd frontend && npm run dev
```

Run backend in another:

```bash
cd backend/app && uv run uvicorn app.main:app --reload
```

Visit `http://localhost:3000/en/stores` in an incognito window. Today this redirects to `/en/login` — that is the bug we are fixing.

---

## File map

| File | Responsibility | Touched by |
|------|----------------|------------|
| `frontend/src/app/(customer)/[locale]/stores/page.tsx` | Store list page; remove guest gate | Task 1 |
| `frontend/src/app/(customer)/[locale]/stores/[id]/page.tsx` | Store detail; remove guest gate | Task 2 |
| `frontend/src/app/(customer)/[locale]/login/page.tsx` | Honor `?next=` post-OTP | Task 3 |
| `frontend/src/lib/CartContext.tsx` | Track `lastSyncDropped` count | Task 4 |
| `frontend/src/components/CartSyncBanner.tsx` | New client component, displays dropped-items banner | Task 5 |
| `frontend/src/app/(customer)/[locale]/layout.tsx` | Mount `CartSyncBanner` inside `CartProvider` | Task 5 |
| `frontend/messages/{en,hi,mr,gu,pa}.json` | Add `Cart.itemsDropped` and `Cart.dismiss` strings | Task 6 |

---

## Task 1: Drop login redirect on store list page

**Files:**
- Modify: `frontend/src/app/(customer)/[locale]/stores/page.tsx`

The store list endpoint `GET /api/v1/stores/` is already public (see `backend/app/src/app/api/__init__.py` and the API surface table in `CLAUDE.md`). The page currently redirects guests to `/login` and only fetches once auth resolves with a `dbUser`. Remove both gates.

- [ ] **Step 1: Replace the auth-gated effect with an unconditional fetch**

Current code (`frontend/src/app/(customer)/[locale]/stores/page.tsx:13-31`):

```tsx
export default function StoresPage() {
  const t = useTranslations("Stores");
  const router = useRouter();
  const { dbUser, loading } = useAuth();
  const [stores, setStores] = useState<Store[]>([]);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (!loading && !dbUser) {
      router.push("/login");
      return;
    }
    if (!loading && dbUser) {
      get<Store[]>("/api/v1/stores/")
        .then(setStores)
        .catch(() => setStores([]))
        .finally(() => setFetching(false));
    }
  }, [loading, dbUser, router]);
```

Replace with:

```tsx
export default function StoresPage() {
  const t = useTranslations("Stores");
  const [stores, setStores] = useState<Store[]>([]);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    get<Store[]>("/api/v1/stores/")
      .then(setStores)
      .catch(() => setStores([]))
      .finally(() => setFetching(false));
  }, []);
```

- [ ] **Step 2: Remove unused imports**

Delete these lines from the top of the file:

```tsx
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
```

- [ ] **Step 3: Update the loading branch**

Current:

```tsx
if (loading || fetching) {
```

Replace with:

```tsx
if (fetching) {
```

- [ ] **Step 4: Lint and typecheck**

Run from `frontend/`:

```bash
npm run lint
```

Expected: no errors related to `stores/page.tsx`. Pre-existing warnings in other files are acceptable. If lint complains about unused imports here, remove them.

- [ ] **Step 5: Manual verification**

In an incognito window, visit `http://localhost:3000/en/stores`. The page must render the store grid without redirecting. Click any store card; navigation to `/en/stores/[id]` should work (Task 2 will fix that page itself).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/\(customer\)/\[locale\]/stores/page.tsx
git commit -m "feat(web): allow guest browsing of store list"
```

---

## Task 2: Drop login redirect on store detail page

**Files:**
- Modify: `frontend/src/app/(customer)/[locale]/stores/[id]/page.tsx`

The store detail endpoint and the catalog endpoints (`/api/v1/stores/{id}`, `/api/v1/stores/{id}/inventory`, `/api/v1/catalog/products`, `/api/v1/catalog/services`, `/api/v1/catalog/categories`, `/api/v1/catalog/subcategories`) are all public. Same pattern as Task 1: drop the login redirect, fetch unconditionally.

- [ ] **Step 1: Replace the auth-gated fetch effect**

Current code at `frontend/src/app/(customer)/[locale]/stores/[id]/page.tsx:118-169`:

```tsx
export default function StoreDetailPage({ params }: Props) {
  const t = useTranslations("StoreDetail");
  const { id } = use(params);
  const storeId = parseInt(id, 10);
  const router = useRouter();
  const { dbUser, loading: authLoading } = useAuth();

  const [store, setStore] = useState<Store | null>(null);
  const [inventory, setInventory] = useState<InventoryWithProduct[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [subcategories, setSubcategories] = useState<Subcategory[]>([]);
  const [fetching, setFetching] = useState(true);
  const [activeAnchor, setActiveAnchor] = useState<string | null>(null);
  const [subcategoryFilters, setSubcategoryFilters] = useState<
    Record<number, number | null>
  >({});

  useEffect(() => {
    if (!authLoading && !dbUser) {
      router.push("/login");
      return;
    }
    if (!authLoading && dbUser) {
      Promise.all([
        get<Store>(`/api/v1/stores/${storeId}`),
        get<StoreInventory[]>(`/api/v1/stores/${storeId}/inventory`),
        get<MasterProduct[]>("/api/v1/catalog/products"),
        get<Service[]>("/api/v1/catalog/services"),
        get<Category[]>("/api/v1/catalog/categories"),
        get<Subcategory[]>("/api/v1/catalog/subcategories").catch(
          () => [] as Subcategory[]
        ),
      ])
        .then(([storeData, invData, products, svcs, cats, subs]) => {
          setStore(storeData);
          setServices(svcs);
          setCategories(cats);
          setSubcategories(subs);
          const productMap = new Map(products.map((p) => [p.id, p]));
          const enriched = invData
            .map((inv) => ({
              ...inv,
              product: productMap.get(inv.product_id)!,
            }))
            .filter((inv) => inv.product);
          setInventory(enriched);
        })
        .catch(() => setStore(null))
        .finally(() => setFetching(false));
    }
  }, [authLoading, dbUser, storeId, router]);
```

Replace with:

```tsx
export default function StoreDetailPage({ params }: Props) {
  const t = useTranslations("StoreDetail");
  const { id } = use(params);
  const storeId = parseInt(id, 10);

  const [store, setStore] = useState<Store | null>(null);
  const [inventory, setInventory] = useState<InventoryWithProduct[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [subcategories, setSubcategories] = useState<Subcategory[]>([]);
  const [fetching, setFetching] = useState(true);
  const [activeAnchor, setActiveAnchor] = useState<string | null>(null);
  const [subcategoryFilters, setSubcategoryFilters] = useState<
    Record<number, number | null>
  >({});

  useEffect(() => {
    Promise.all([
      get<Store>(`/api/v1/stores/${storeId}`),
      get<StoreInventory[]>(`/api/v1/stores/${storeId}/inventory`),
      get<MasterProduct[]>("/api/v1/catalog/products"),
      get<Service[]>("/api/v1/catalog/services"),
      get<Category[]>("/api/v1/catalog/categories"),
      get<Subcategory[]>("/api/v1/catalog/subcategories").catch(
        () => [] as Subcategory[]
      ),
    ])
      .then(([storeData, invData, products, svcs, cats, subs]) => {
        setStore(storeData);
        setServices(svcs);
        setCategories(cats);
        setSubcategories(subs);
        const productMap = new Map(products.map((p) => [p.id, p]));
        const enriched = invData
          .map((inv) => ({
            ...inv,
            product: productMap.get(inv.product_id)!,
          }))
          .filter((inv) => inv.product);
        setInventory(enriched);
      })
      .catch(() => setStore(null))
      .finally(() => setFetching(false));
  }, [storeId]);
```

- [ ] **Step 2: Remove unused imports**

Delete these lines from the top of the file:

```tsx
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
```

- [ ] **Step 3: Lint and typecheck**

```bash
cd frontend && npm run lint
```

Expected: no errors in `stores/[id]/page.tsx`.

- [ ] **Step 4: Manual verification**

In an incognito window:

1. Visit `http://localhost:3000/en/stores/1` (or any seeded store id).
2. Verify the store renders with services sidebar, categories, products.
3. Click "Add" on a product; verify the cart count in the navbar increments.
4. Open DevTools → Application → Local Storage → `kb_carts`. The item must appear there.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/\(customer\)/\[locale\]/stores/\[id\]/page.tsx
git commit -m "feat(web): allow guest browsing of store detail + cart add"
```

---

## Task 3: Honor `?next=` on the login page

**Files:**
- Modify: `frontend/src/app/(customer)/[locale]/login/page.tsx`

Customers arriving from `/cart` or `/checkout/[storeId]` already get linked to `/login?next=/checkout/[storeId]`. Login currently ignores the param. Customers should land on the `next` target post-OTP. Admins and sellers must continue to land on their dashboards (their `?next=` is dropped to prevent landing on customer-only pages).

`useSearchParams` in a client component must be wrapped in `<Suspense>` (the same pattern is already used at `frontend/src/app/(operator)/seller/signup/page.tsx:1138-1144`). Do that here too — the existing component becomes `LoginPageInner` and the `default export` wraps it in `Suspense`.

- [ ] **Step 1: Update imports**

At the top of `frontend/src/app/(customer)/[locale]/login/page.tsx`, change:

```tsx
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
```

to:

```tsx
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
```

- [ ] **Step 2: Add `safeNext` and `resolveTarget` helpers**

Below the existing `getRedirect` function (around line 17), add:

```tsx
function safeNext(raw: string | null): string | null {
  if (!raw) return null;
  if (!raw.startsWith("/")) return null;
  if (raw.startsWith("//")) return null;
  if (raw.includes("\\")) return null;
  return raw;
}

function resolveTarget(user: User, nextRaw: string | null): string {
  if (user.role !== "customer") return getRedirect(user);
  return safeNext(nextRaw) ?? getRedirect(user);
}
```

- [ ] **Step 3: Rename the existing component to `LoginPageInner` and read `next`**

Change the existing `export default function LoginPage()` declaration on line 19 to:

```tsx
function LoginPageInner() {
```

(remove `export default`). Inside the function, after the existing `const router = useRouter();` line, add:

```tsx
const params = useSearchParams();
const nextParam = params.get("next");
```

Replace the three `router.push(getRedirect(...))` call sites with `resolveTarget`:

Already-logged-in effect (was line 33):

```tsx
router.push(resolveTarget(dbUser, nextParam));
```

Existing-user OTP verify (was line 68):

```tsx
router.push(resolveTarget(result.user, nextParam));
```

New-user post-name verify (was line 88):

```tsx
router.push(resolveTarget(result.user, nextParam));
```

Update the `useEffect` dependency array (was line 34) to include `nextParam`:

```tsx
}, [dbUser, router, nextParam]);
```

- [ ] **Step 4: Add a Suspense-wrapping default export**

At the very bottom of the file, after the `LoginPageInner` closing brace, add:

```tsx
export default function LoginPage() {
  return (
    <Suspense fallback={<div style={{ minHeight: "100vh" }} />}>
      <LoginPageInner />
    </Suspense>
  );
}
```

- [ ] **Step 5: Lint and typecheck**

```bash
cd frontend && npm run lint
```

Expected: no errors in `login/page.tsx`.

- [ ] **Step 6: Manual verification**

In an incognito window:

1. Visit `http://localhost:3000/en/stores/1`, add an item.
2. Click cart icon → cart page → "Login & checkout".
3. URL must be `/en/login?next=/checkout/1`.
4. Complete OTP (use `EMAIL_PROVIDER=console` and copy the code from the backend log).
5. Post-verify, you must land on `/en/checkout/1` (NOT `/stores`).
6. Verify open-redirect guard: visit `http://localhost:3000/en/login?next=https://example.com`, complete OTP. You must land on `/stores`, not example.com.
7. Verify role precedence: log in as a seller (admin) account with `?next=/checkout/1`. They must land on `/seller` (`/admin`), not `/checkout/1`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/\(customer\)/\[locale\]/login/page.tsx
git commit -m "feat(web): honor ?next= on login for customer redirect after OTP"
```

---

## Task 4: Track dropped-items count in CartContext

**Files:**
- Modify: `frontend/src/lib/CartContext.tsx`

`remoteCart.syncCarts` already returns `{ carts, dropped }` (see `frontend/src/lib/remoteCart.ts:79-85`). The context destructures only `result.carts` today. Add a `lastSyncDropped: number` to the context, set it to `result.dropped.length` after sync, and expose a `clearSyncDropped()` callback so the banner can dismiss it.

- [ ] **Step 1: Add `lastSyncDropped` to the context type**

In `frontend/src/lib/CartContext.tsx`, change the `CartContextValue` interface (lines 19-30) to:

```tsx
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
  refresh: () => Promise<void>;
  lastSyncDropped: number;
  clearSyncDropped: () => void;
}
```

- [ ] **Step 2: Add the state inside `CartProvider`**

After `const [loading, setLoading] = useState<boolean>(true);` (line 42), add:

```tsx
const [lastSyncDropped, setLastSyncDropped] = useState<number>(0);
```

- [ ] **Step 3: Capture drop count after sync**

In the login-transition effect (lines 87-103), the current code is:

```tsx
const result = await remoteCart.syncCarts(token, payload);
if (!cancelled) setCarts(result.carts);
localCart.clearAllCarts();
```

Change to:

```tsx
const result = await remoteCart.syncCarts(token, payload);
if (!cancelled) {
  setCarts(result.carts);
  setLastSyncDropped(result.dropped.length);
}
localCart.clearAllCarts();
```

- [ ] **Step 4: Add a `clearSyncDropped` callback**

After the `clearStoreCart` `useCallback` (around line 232), add:

```tsx
const clearSyncDropped = useCallback(() => {
  setLastSyncDropped(0);
}, []);
```

- [ ] **Step 5: Expose new fields on the context value**

Update the `value` object (around line 237):

```tsx
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
  refresh,
  lastSyncDropped,
  clearSyncDropped,
};
```

- [ ] **Step 6: Lint and typecheck**

```bash
cd frontend && npm run lint
```

Expected: no errors in `CartContext.tsx`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/CartContext.tsx
git commit -m "feat(web): expose lastSyncDropped count from CartContext"
```

---

## Task 5: Add CartSyncBanner component and mount it

**Files:**
- Create: `frontend/src/components/CartSyncBanner.tsx`
- Modify: `frontend/src/app/(customer)/[locale]/layout.tsx`

The customer layout is an async server component, so the banner must be a client component sitting inside `CartProvider`. Banner reads `lastSyncDropped` from `useCart()`, renders when `> 0`, and dismisses by calling `clearSyncDropped()`.

- [ ] **Step 1: Create the banner component**

Create `frontend/src/components/CartSyncBanner.tsx`:

```tsx
"use client";

import { useTranslations } from "next-intl";
import { useCart } from "@/lib/CartContext";

export default function CartSyncBanner() {
  const t = useTranslations("Cart");
  const { lastSyncDropped, clearSyncDropped } = useCart();

  if (lastSyncDropped <= 0) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        background: "var(--color-warning-bg, #fff7e6)",
        color: "var(--color-warning-fg, #92400e)",
        borderBottom: "1px solid var(--color-warning-border, #fcd34d)",
        padding: "0.75rem 1rem",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: "1rem",
        fontSize: "0.9rem",
      }}
    >
      <span>{t("itemsDropped", { count: lastSyncDropped })}</span>
      <button
        type="button"
        onClick={clearSyncDropped}
        style={{
          background: "transparent",
          border: 0,
          cursor: "pointer",
          fontWeight: 600,
          color: "inherit",
        }}
      >
        {t("dismiss")}
      </button>
    </div>
  );
}
```

Note: inline styles used because no toast component exists in the design system and the user instruction is to avoid new dependencies. Tokens like `--color-warning-bg` will fall back to literal hex values in browsers without the variables defined; this matches the spec's "no new dependency, no UI redesign" boundary.

- [ ] **Step 2: Mount the banner in the customer layout**

Edit `frontend/src/app/(customer)/[locale]/layout.tsx`. At the top, add:

```tsx
import CartSyncBanner from "@/components/CartSyncBanner";
```

Then change the JSX inside `CartProvider` (currently lines 79-83):

```tsx
<CartProvider>
  <Navbar />
  <main>{children}</main>
  <Footer />
</CartProvider>
```

to:

```tsx
<CartProvider>
  <CartSyncBanner />
  <Navbar />
  <main>{children}</main>
  <Footer />
</CartProvider>
```

- [ ] **Step 3: Lint and typecheck**

```bash
cd frontend && npm run lint
```

Expected: no errors. If lint complains about the inline-style bag, that is acceptable for a spike component; suppress only if the project's existing code style permits it.

- [ ] **Step 4: Manual verification (deferred to Task 7)**

The banner cannot be tested until the i18n keys exist. Task 6 adds them; Task 7 runs the end-to-end smoke test.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/CartSyncBanner.tsx frontend/src/app/\(customer\)/\[locale\]/layout.tsx
git commit -m "feat(web): show banner when guest-cart sync drops items"
```

---

## Task 6: Add i18n keys for the drop banner

**Files:**
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/hi.json`
- Modify: `frontend/messages/mr.json`
- Modify: `frontend/messages/gu.json`
- Modify: `frontend/messages/pa.json`

Add two keys under the existing `Cart` namespace in each locale file: `itemsDropped` (with ICU plural for `count`) and `dismiss`.

- [ ] **Step 1: Edit `frontend/messages/en.json`**

Find the `"Cart": { ... }` block. Add inside it (preserve trailing-comma rules):

```json
    "itemsDropped": "{count, plural, one {# item from your guest cart was unavailable and removed.} other {# items from your guest cart were unavailable and removed.}}",
    "dismiss": "Dismiss"
```

- [ ] **Step 2: Edit `frontend/messages/hi.json`**

Add inside `Cart`:

```json
    "itemsDropped": "{count, plural, one {आपकी गेस्ट कार्ट से # आइटम उपलब्ध नहीं था और हटा दिया गया।} other {आपकी गेस्ट कार्ट से # आइटम उपलब्ध नहीं थे और हटा दिए गए।}}",
    "dismiss": "बंद करें"
```

- [ ] **Step 3: Edit `frontend/messages/mr.json`**

Add inside `Cart`:

```json
    "itemsDropped": "{count, plural, one {तुमच्या पाहुण्या कार्टमधील # वस्तू उपलब्ध नव्हती आणि काढून टाकली.} other {तुमच्या पाहुण्या कार्टमधील # वस्तू उपलब्ध नव्हत्या आणि काढून टाकल्या.}}",
    "dismiss": "बंद करा"
```

- [ ] **Step 4: Edit `frontend/messages/gu.json`**

Add inside `Cart`:

```json
    "itemsDropped": "{count, plural, one {તમારી ગેસ્ટ કાર્ટમાંથી # વસ્તુ ઉપલબ્ધ નહોતી અને દૂર કરવામાં આવી.} other {તમારી ગેસ્ટ કાર્ટમાંથી # વસ્તુઓ ઉપલબ્ધ નહોતી અને દૂર કરવામાં આવી.}}",
    "dismiss": "બંધ કરો"
```

- [ ] **Step 5: Edit `frontend/messages/pa.json`**

Add inside `Cart`:

```json
    "itemsDropped": "{count, plural, one {ਤੁਹਾਡੇ ਮਹਿਮਾਨ ਕਾਰਟ ਵਿੱਚੋਂ # ਆਈਟਮ ਉਪਲਬਧ ਨਹੀਂ ਸੀ ਅਤੇ ਹਟਾ ਦਿੱਤੀ ਗਈ।} other {ਤੁਹਾਡੇ ਮਹਿਮਾਨ ਕਾਰਟ ਵਿੱਚੋਂ # ਆਈਟਮਾਂ ਉਪਲਬਧ ਨਹੀਂ ਸਨ ਅਤੇ ਹਟਾ ਦਿੱਤੀਆਂ ਗਈਆਂ।}}",
    "dismiss": "ਬੰਦ ਕਰੋ"
```

- [ ] **Step 6: Validate JSON**

Run from the repo root:

```bash
for f in frontend/messages/{en,hi,mr,gu,pa}.json; do
  python3 -c "import json,sys; json.load(open('$f')); print('OK $f')"
done
```

Expected: `OK` line per file. Any `JSONDecodeError` means a comma is misplaced — fix and re-run.

- [ ] **Step 7: Commit**

```bash
git add frontend/messages/{en,hi,mr,gu,pa}.json
git commit -m "feat(i18n): add Cart.itemsDropped + Cart.dismiss strings in 5 locales"
```

---

## Task 7: End-to-end smoke test

No automated frontend tests exist for this codebase, so the verification is a manual walkthrough. Run both backend and frontend, then execute every step.

- [ ] **Step 1: Confirm backend, Celery worker, frontend are all running**

Three terminals:

```bash
# Terminal 1
docker-compose up -d
cd backend/app && uv run uvicorn app.main:app --reload

# Terminal 2
cd backend/app && uv run celery -A app.core.celery_app worker --loglevel=info

# Terminal 3
cd frontend && npm run dev
```

Backend env: `EMAIL_PROVIDER=console` so OTP codes appear in the backend log.

- [ ] **Step 2: Guest browse**

Open an incognito window, visit `http://localhost:3000/en/stores`. Expect: store grid loads, no redirect.

- [ ] **Step 3: Guest add to cart**

Click any store. Add 2 different products. Open cart icon in navbar. Expect: count reflects added items. Open DevTools → Application → Local Storage. Expect: `kb_carts` contains the items.

- [ ] **Step 4: Guest cart page**

Visit `/en/cart`. Expect: per-store cart shows items, "Login & checkout" link visible, link href is `/en/login?next=/checkout/<storeId>`.

- [ ] **Step 5: Login → cart merge**

Click "Login & checkout". On the login page, enter a customer email, copy the OTP from the backend log, complete verification (and full-name step if new user). Expect: post-verify, URL is `/en/checkout/<storeId>` (NOT `/en/stores`).

- [ ] **Step 6: Server-side cart contains the merged items**

Open DevTools → Network → filter `carts`. Trigger a refresh of the checkout page. Expect: `GET /api/v1/carts` response contains the items added as guest. Local storage `kb_carts` is now empty (or `[]`).

- [ ] **Step 7: Drop notification**

Repeat steps 2-3 in a fresh incognito window. Before logging in, in another browser session as a seller, mark one of the cart's inventory rows `is_available=false` (via the seller dashboard or a manual SQL update against `khanabazaar` DB on table `storeinventory`). Then in the guest window, log in. Expect: the orange `CartSyncBanner` appears at the top of the page reading "1 item from your guest cart was unavailable and removed." Click "Dismiss"; the banner disappears.

- [ ] **Step 8: Open-redirect guard**

In a fresh incognito window, visit `http://localhost:3000/en/login?next=https://example.com`. Complete OTP. Expect: post-verify URL is `/en/stores`, not `https://example.com`. Repeat with `?next=//example.com` and `?next=/\\example.com` — same result.

- [ ] **Step 9: Role precedence**

Log out, then in a fresh incognito window visit `http://localhost:3000/en/login?next=/checkout/1`. Use a seller account email. Expect: post-verify URL is `/seller`, not `/checkout/1`. Repeat with an admin email; expect `/admin`.

- [ ] **Step 10: Lint + typecheck full project**

```bash
cd frontend && npm run lint
```

Expected: no new errors introduced by this branch.

- [ ] **Step 11: Final commit (only if any fixes were needed during the smoke test)**

If steps 7-9 surfaced bugs, fix them inline and commit individually. Do not create a single catch-all "fixes from smoke test" commit — keep the history readable.

---

## Self-review checklist (already completed by plan author)

**Spec coverage:**
- Spec § "Affected files" → covered by Tasks 1-6.
- Spec § "Login redirect logic" → Task 3 with `safeNext` matching the spec snippet exactly.
- Spec § "Drop notification UX" → Tasks 4-6.
- Spec § "Test plan" → Task 7.
- Spec § "Edge cases" → covered conceptually by Task 7 steps 7-9; no separate task needed since they describe expected behavior, not new code.

**Placeholder scan:** None.

**Type consistency:** `lastSyncDropped: number` and `clearSyncDropped: () => void` are introduced in Task 4 and consumed unchanged in Task 5. `safeNext` and `resolveTarget` are introduced in Task 3 with consistent signatures. i18n keys `Cart.itemsDropped` and `Cart.dismiss` are introduced in Task 6 and consumed unchanged in Task 5.

**Scope:** This plan stays within the spec's stated boundary — frontend-only, no backend changes, no design-system additions, no new dependencies. Suitable for a single PR.
