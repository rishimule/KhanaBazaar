# Saved-address Delivery Picker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface saved customer addresses in the navbar `DeliveryLocationPicker` modal and auto-set the global `DeliveryLocation` to the customer's default saved address on login when the location is still the Mumbai fallback.

**Architecture:** New `CustomerAddressesContext` provider fetches `GET /api/v1/customers/me` once per customer session and exposes addresses to consumers. New `DeliveryLocationAutoSync` side-effect component runs once when the customer logs in and the location is still the fallback. The existing `DeliveryLocationPicker` modal gains a saved-address rows section above autocomplete + map. `DeliveryLocationContext` gains a `hydrated` flag so AutoSync waits until `localStorage` is fully read.

**Tech Stack:** Next.js 16.1 App Router, React 19.2, TypeScript 5, CSS Modules. Frontend-only changes. No backend changes.

**Spec:** `docs/superpowers/specs/2026-05-20-saved-address-delivery-picker-design.md`

**Note on testing:** Frontend has no test runner per `CLAUDE.md`. Each task verifies via `npm run lint`, `npx tsc --noEmit`, and the manual verification checklist in the final task.

---

## File Structure

**Files created:**
- `frontend/src/lib/CustomerAddressesContext.tsx` — provider + `useCustomerAddresses` hook.
- `frontend/src/components/DeliveryLocationAutoSync.tsx` — side-effect component.

**Files modified:**
- `frontend/src/lib/DeliveryLocationContext.tsx` — add `hydrated` flag and export `isDefaultDeliveryLocation` helper.
- `frontend/src/components/DeliveryLocationPicker.tsx` — render saved-address section.
- `frontend/src/components/DeliveryLocationPicker.module.css` — new styles for saved-address rows.
- `frontend/src/app/(customer)/[locale]/layout.tsx` — wire provider + AutoSync into tree.

**Files untouched:**
- `frontend/src/app/(operator)/layout.tsx`
- `frontend/src/components/orders/AddressPicker.tsx`
- Any backend file.

---

## Task 1: Add `hydrated` flag and `isDefaultDeliveryLocation` to `DeliveryLocationContext`

**Files:**
- Modify: `frontend/src/lib/DeliveryLocationContext.tsx`

- [ ] **Step 1: Add `hydrated` to the context value type**

Replace the existing `DeliveryLocationContextValue` interface:

```tsx
interface DeliveryLocationContextValue {
  location: DeliveryLocation;
  /** False until the initial localStorage hydration effect has completed. */
  hydrated: boolean;
  setLocation: (loc: DeliveryLocation | null) => void;
  clear: () => void;
}
```

- [ ] **Step 2: Track `hydrated` state inside the provider**

Inside `DeliveryLocationProvider`, alongside `setLocationState`, add:

```tsx
const [hydrated, setHydrated] = useState(false);
```

At the end of the existing hydration `useEffect` (the one that reads from `localStorage` on mount), after the `try { ... } catch { }` block but **before** the `onStorage` listener registration, add:

```tsx
setHydrated(true);
```

So the effect body looks like:

```tsx
useEffect(() => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time hydration from localStorage on mount
    if (raw) setLocationState(JSON.parse(raw));
  } catch {
    // localStorage unavailable / corrupted JSON — ignore.
  }
  setHydrated(true);

  const onStorage = (e: StorageEvent) => {
    // ...existing listener body...
  };
  window.addEventListener("storage", onStorage);
  return () => window.removeEventListener("storage", onStorage);
}, []);
```

- [ ] **Step 3: Include `hydrated` in the memoized context value**

Replace the existing `value` memo:

```tsx
const value = useMemo(
  () => ({ location, hydrated, setLocation, clear }),
  [location, hydrated, setLocation, clear],
);
```

- [ ] **Step 4: Export `isDefaultDeliveryLocation` helper**

After `clearStoredDeliveryLocation` at the bottom of the file, add:

```tsx
/** True when `loc` is exactly the Mumbai fallback. Used by
 *  DeliveryLocationAutoSync to decide whether to overwrite. */
export function isDefaultDeliveryLocation(loc: DeliveryLocation): boolean {
  return (
    loc.lat === DEFAULT_DELIVERY_LOCATION.lat &&
    loc.lng === DEFAULT_DELIVERY_LOCATION.lng &&
    loc.label === DEFAULT_DELIVERY_LOCATION.label
  );
}
```

- [ ] **Step 5: Type-check + lint**

Run from `frontend/`:

```bash
npx tsc --noEmit
npm run lint
```

Expected: both pass. (TS may flag any existing consumer that destructures the context value without `hydrated` — those keep working because the new field is additive, not required by destructure.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/DeliveryLocationContext.tsx
git commit -m "feat(delivery-location): add hydrated flag and fallback helper"
```

---

## Task 2: Create `CustomerAddressesContext` provider + hook

**Files:**
- Create: `frontend/src/lib/CustomerAddressesContext.tsx`

- [ ] **Step 1: Write the provider file**

Create `frontend/src/lib/CustomerAddressesContext.tsx` with:

```tsx
"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
} from "react";

import { get } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import type { CustomerAddress, CustomerProfile } from "@/types";

interface CustomerAddressesContextValue {
  /** Full list as returned by the API, already sorted desc(is_default), id. */
  addresses: CustomerAddress[];
  /** First address with is_default === true, else null. */
  defaultAddress: CustomerAddress | null;
  /** True while a fetch is in flight. False once the first attempt settles. */
  loading: boolean;
  /** Human-readable error from the last fetch attempt, else null. */
  error: string | null;
  /** Trigger a re-fetch. No-op if the gate conditions aren't met. */
  refetch: () => void;
}

const EMPTY: CustomerAddressesContextValue = {
  addresses: [],
  defaultAddress: null,
  loading: false,
  error: null,
  refetch: () => {},
};

const CustomerAddressesContext =
  createContext<CustomerAddressesContextValue | null>(null);

export function CustomerAddressesProvider(
  { children }: { children: React.ReactNode },
) {
  const auth = useAuth();
  const [addresses, setAddresses] = useState<CustomerAddress[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fetchNonce, setFetchNonce] = useState(0);

  const role = auth.dbUser?.role ?? null;
  const token = auth.token;
  const authLoading = auth.loading;

  useEffect(() => {
    // Reset to empty for non-customers / logged-out users.
    if (authLoading) return;
    if (!token || role !== "customer") {
      setAddresses([]);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    get<CustomerProfile>("/api/v1/customers/me", token)
      .then((profile) => {
        if (cancelled) return;
        setAddresses(profile.addresses);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load addresses");
        setAddresses([]);
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, [token, role, authLoading, fetchNonce]);

  const refetch = useCallback(() => {
    setFetchNonce((n) => n + 1);
  }, []);

  const defaultAddress = useMemo(
    () => addresses.find((a) => a.is_default) ?? null,
    [addresses],
  );

  const value = useMemo<CustomerAddressesContextValue>(
    () => ({ addresses, defaultAddress, loading, error, refetch }),
    [addresses, defaultAddress, loading, error, refetch],
  );

  return (
    <CustomerAddressesContext.Provider value={value}>
      {children}
    </CustomerAddressesContext.Provider>
  );
}

export function useCustomerAddresses(): CustomerAddressesContextValue {
  const ctx = useContext(CustomerAddressesContext);
  // If the provider is not mounted (e.g. operator routes), degrade to empty.
  if (!ctx) return EMPTY;
  return ctx;
}
```

- [ ] **Step 2: Type-check + lint**

Run from `frontend/`:

```bash
npx tsc --noEmit
npm run lint
```

Expected: both pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/CustomerAddressesContext.tsx
git commit -m "feat(customer-addresses): add provider + hook"
```

---

## Task 3: Create `DeliveryLocationAutoSync` component

**Files:**
- Create: `frontend/src/components/DeliveryLocationAutoSync.tsx`

- [ ] **Step 1: Write the component file**

Create `frontend/src/components/DeliveryLocationAutoSync.tsx` with:

```tsx
"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useRef } from "react";

import { useAuth } from "@/lib/AuthContext";
import { useCustomerAddresses } from "@/lib/CustomerAddressesContext";
import {
  isDefaultDeliveryLocation,
  useDeliveryLocation,
} from "@/lib/DeliveryLocationContext";
import { formatAddress } from "@/lib/format-address";
import { truncateLabel } from "@/lib/geo";
import type { CustomerAddress } from "@/types";

function pickAutoSyncAddress(
  defaultAddress: CustomerAddress | null,
  addresses: CustomerAddress[],
): CustomerAddress | null {
  const hasCoords = (a: CustomerAddress) =>
    a.address.latitude != null && a.address.longitude != null;
  if (defaultAddress && hasCoords(defaultAddress)) return defaultAddress;
  return addresses.find(hasCoords) ?? null;
}

/** Side-effect-only component. Runs once per (token, dbUser.id) when the
 *  logged-in customer's stored DeliveryLocation is still the Mumbai fallback,
 *  setting it to their default saved address. Renders nothing. */
export function DeliveryLocationAutoSync() {
  const auth = useAuth();
  const { location, hydrated, setLocation } = useDeliveryLocation();
  const { addresses, defaultAddress, loading } = useCustomerAddresses();
  const didSyncRef = useRef(false);

  // Reset the one-shot when the identity changes so a second customer
  // signing in on the same tab also gets auto-synced.
  useEffect(() => {
    didSyncRef.current = false;
  }, [auth.token, auth.dbUser?.id]);

  useEffect(() => {
    if (didSyncRef.current) return;
    if (auth.loading || !hydrated || loading) return;
    if (!auth.token || auth.dbUser?.role !== "customer") return;
    if (!isDefaultDeliveryLocation(location)) return;

    const target = pickAutoSyncAddress(defaultAddress, addresses);
    if (!target) return;
    if (target.address.latitude == null || target.address.longitude == null) return;

    setLocation({
      lat: target.address.latitude,
      lng: target.address.longitude,
      label: truncateLabel(formatAddress(target.address), 40),
    });
    didSyncRef.current = true;
  }, [
    auth.loading,
    auth.token,
    auth.dbUser?.role,
    hydrated,
    loading,
    location,
    defaultAddress,
    addresses,
    setLocation,
  ]);

  return null;
}
```

- [ ] **Step 2: Type-check + lint**

Run from `frontend/`:

```bash
npx tsc --noEmit
npm run lint
```

Expected: both pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/DeliveryLocationAutoSync.tsx
git commit -m "feat(delivery-location): add auto-sync on customer login"
```

---

## Task 4: Render saved-address rows in `DeliveryLocationPicker`

**Files:**
- Modify: `frontend/src/components/DeliveryLocationPicker.tsx`

- [ ] **Step 1: Add imports**

Top of `DeliveryLocationPicker.tsx`, add to the existing import block:

```tsx
import { useCustomerAddresses } from "@/lib/CustomerAddressesContext";
import { useAuth } from "@/lib/AuthContext";
import { formatAddress } from "@/lib/format-address";
import type { CustomerAddress } from "@/types";
```

- [ ] **Step 2: Read context inside the component**

Inside `DeliveryLocationPicker`, just below `const { setLocation } = useDeliveryLocation();`, add:

```tsx
const auth = useAuth();
const { addresses } = useCustomerAddresses();

const savedRows: CustomerAddress[] =
  auth.dbUser?.role === "customer"
    ? addresses.filter(
        (a) => a.address.latitude != null && a.address.longitude != null,
      )
    : [];
```

- [ ] **Step 3: Add the saved-address pick handler**

Below `onMapPlace`, add:

```tsx
const onSavedAddress = (a: CustomerAddress) => {
  if (a.address.latitude == null || a.address.longitude == null) return;
  setStaged({
    lat: a.address.latitude,
    lng: a.address.longitude,
    label: truncateLabel(formatAddress(a.address), 40),
  });
  setError(null);
};
```

- [ ] **Step 4: Render the saved-address section**

Inside the returned `<Modal>` body, replace the `<div className={styles.body}>` block with:

```tsx
<div className={styles.body}>
  {savedRows.length > 0 && (
    <div className={styles.savedSection}>
      <p className={styles.savedHeading}>Saved addresses</p>
      <ul className={styles.savedList}>
        {savedRows.map((a) => (
          <li key={a.id}>
            <button
              type="button"
              className={styles.savedRow}
              onClick={() => onSavedAddress(a)}
            >
              <span className={styles.savedTitle}>
                {a.label ?? "Address"}
                {a.is_default && (
                  <span className={styles.defaultPill}>Default</span>
                )}
              </span>
              <span className={styles.savedBody}>
                {formatAddress(a.address)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )}
  <AddressAutocomplete onPlace={onAutocompletePlace} />
  <p className={styles.or}>
    {savedRows.length > 0 ? "or pick a new location" : "or pin on map"}
  </p>
  <MapPicker
    initialLat={staged?.lat}
    initialLng={staged?.lng}
    target={mapTarget}
    onPlace={onMapPlace}
    onError={setError}
  />
  {error && <span className={styles.error}>{error}</span>}
</div>
```

(The original mockup divider used `styles.or` between autocomplete and map; this preserves the existing divider text when no saved rows are present, and reuses the same component for the "or pick a new location" wording when saved rows exist.)

- [ ] **Step 5: Type-check + lint**

Run from `frontend/`:

```bash
npx tsc --noEmit
npm run lint
```

Expected: both pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/DeliveryLocationPicker.tsx
git commit -m "feat(delivery-location): render saved addresses in picker"
```

---

## Task 5: Add CSS for the saved-address section

**Files:**
- Modify: `frontend/src/components/DeliveryLocationPicker.module.css`

- [ ] **Step 1: Append the new rules**

Append to the end of `frontend/src/components/DeliveryLocationPicker.module.css`:

```css
.savedSection {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.savedHeading {
  margin: 0;
  font-size: var(--body-sm);
  font-weight: var(--weight-semibold);
  color: var(--shade-cool-base-7);
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.savedList {
  display: flex;
  flex-direction: column;
  gap: 8px;
  list-style: none;
  padding: 0;
  margin: 0;
}

.savedRow {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  text-align: left;
  padding: 12px 14px;
  background: var(--white);
  border: 1px solid var(--shade-cool-light-4);
  border-radius: var(--radius-card);
  font-family: var(--font-family-sans);
  font-size: var(--body-base);
  cursor: pointer;
  transition: border-color var(--duration-fast), background var(--duration-fast);
}

.savedRow:hover {
  border-color: var(--color-btn-primary-bg);
  background: var(--shade-cool-light-6);
}

.savedRow:focus-visible {
  outline: 2px solid var(--color-btn-primary-bg);
  outline-offset: 2px;
}

.savedTitle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: var(--weight-semibold);
  color: var(--shade-cool-dark-1);
}

.defaultPill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--color-btn-primary-bg);
  color: var(--white);
  font-size: var(--body-xs);
  font-weight: var(--weight-medium);
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.savedBody {
  color: var(--shade-cool-base-5);
  font-size: var(--body-sm);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
```

- [ ] **Step 2: Lint**

Run from `frontend/`:

```bash
npm run lint
```

Expected: pass. (No CSS lint configured separately; ESLint covers JSX usage of the new class names — they're already referenced from Task 4.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/DeliveryLocationPicker.module.css
git commit -m "style(delivery-location): saved address row styles"
```

---

## Task 6: Wire `CustomerAddressesProvider` + `DeliveryLocationAutoSync` into the customer layout

**Files:**
- Modify: `frontend/src/app/(customer)/[locale]/layout.tsx`

- [ ] **Step 1: Add imports**

In the import block at the top of `frontend/src/app/(customer)/[locale]/layout.tsx`, add:

```tsx
import { CustomerAddressesProvider } from "@/lib/CustomerAddressesContext";
import { DeliveryLocationAutoSync } from "@/components/DeliveryLocationAutoSync";
```

- [ ] **Step 2: Wrap CartProvider with CustomerAddressesProvider and mount AutoSync**

Replace the existing provider tree inside `<body>`:

```tsx
<body>
  <NextIntlClientProvider messages={messages}>
    <AuthProvider>
      <DeliveryLocationProvider>
        <CustomerAddressesProvider>
          <DeliveryLocationAutoSync />
          <CartProvider>
            <Navbar />
            <CartSyncBanner />
            <main>{children}</main>
            <Footer />
          </CartProvider>
        </CustomerAddressesProvider>
      </DeliveryLocationProvider>
    </AuthProvider>
  </NextIntlClientProvider>
  <ServiceWorkerRegistrar />
</body>
```

- [ ] **Step 3: Type-check + lint**

Run from `frontend/`:

```bash
npx tsc --noEmit
npm run lint
```

Expected: both pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/(customer)/[locale]/layout.tsx
git commit -m "feat(layout): wire customer addresses provider + auto-sync"
```

---

## Task 7: Manual verification

**Files:**
- None.

Bring up the dev stack and walk the checklist. Frontend has no automated tests for this layer (`CLAUDE.md`), so this task is the integration gate.

- [ ] **Step 1: Start dev stack**

Run from repo root:

```bash
./scripts/dev.sh start
```

Wait until the script reports backend + frontend healthy. Then open `http://localhost:3000`.

- [ ] **Step 2: Verify guest path**

Without logging in, click the "Deliver to" chip in the navbar.

Expected: modal opens with the autocomplete input and the map only. **No** "Saved addresses" heading or rows. Divider text reads "or pin on map".

- [ ] **Step 3: Verify auto-sync on login**

Log in as a customer who has at least one saved address with lat/lng. After login resolves, look at the navbar chip.

Expected: chip text updates from "Mumbai, Maharashtra, India" to a truncated form of the customer's default address.

- [ ] **Step 4: Verify saved-address pick**

Click the "Deliver to" chip.

Expected: the "Saved addresses" section is present above the autocomplete and map, listing every coord-bearing saved address. The default address shows a "Default" pill. Tap a non-default row → "Confirm location" enables → click Confirm → modal closes → chip shows the picked row's label.

- [ ] **Step 5: Verify guest pick preserved across login**

Log out. As a guest, set a location via the map. Then log in.

Expected: chip retains the guest's pick (auto-sync skipped because location ≠ Mumbai fallback).

- [ ] **Step 6: Verify logout resets**

While logged in with a non-fallback location, click "Log out".

Expected: chip resets to "Mumbai, Maharashtra, India".

- [ ] **Step 7: Verify coordless filter**

In the dev DB, mark one of the test customer's addresses with `latitude = null` and `longitude = null` (e.g. via psql or by editing it through `/account/settings` and clearing the map pin if the UI allows). Reload the app and open the picker.

Expected: the coordless row does **not** appear in the saved-address list. Coord-bearing rows still render.

- [ ] **Step 8: Verify operator routes are unaffected**

Log in as a seller (or admin). Visit `/seller` (or `/admin`). Open browser devtools → Network tab.

Expected: no `/api/v1/customers/me` request fires from any operator route. The "Deliver to" chip on operator pages, if visible, behaves as the fallback (no auto-sync).

- [ ] **Step 9: Verify cross-tab logout**

Open the app in two tabs as the same customer. Log out from tab A.

Expected: tab B's chip resets to "Mumbai, Maharashtra, India" within a second (storage event from `DeliveryLocationContext`'s listener). The picker in tab B no longer shows saved addresses on next open.

- [ ] **Step 10: Stop dev stack**

```bash
./scripts/dev.sh stop
```

- [ ] **Step 11: Final commit (only if any small follow-up fixes were needed during manual QA)**

If manual verification surfaced no issues, skip this step. Otherwise, address the issue with a small commit:

```bash
git add <paths>
git commit -m "fix(delivery-location): <description>"
```

---

## Done criteria

- All six implementation tasks committed on a single feature branch (e.g., `feat/saved-address-delivery-picker`).
- Every step in Task 7 passes.
- `npx tsc --noEmit` and `npm run lint` pass on the final commit.
- No backend code modified.
