# Saved-address Delivery Location Picker — Design

**Date:** 2026-05-20
**Scope:** Frontend only. No backend changes.

## Problem

Customers manage saved addresses under `/account/settings` (home, office, …), but the global "Deliver to" picker in the navbar (`DeliveryLocationPicker`) ignores them. To set the storefront's delivery location, a logged-in customer must re-search for or re-pin an address they have already saved. After login, the chip still shows the Mumbai fallback (`DEFAULT_DELIVERY_LOCATION`) until the customer manually changes it.

## Goal

1. Surface saved customer addresses as one-tap options inside the `DeliveryLocationPicker` modal.
2. Auto-set the global `DeliveryLocation` to the customer's default saved address on login, but only when the customer has not already picked something (the location still equals `DEFAULT_DELIVERY_LOCATION`).

## Non-goals

- Saving a newly picked map pin back to the customer's address book from this modal.
- Per-store serviceability filtering inside this modal (it sets a global location, store-agnostic; the checkout `AddressPicker` already handles per-store serviceability).
- Backend changes — no new schema, no new endpoint, no new `default_delivery_address_id` column.
- Touching the checkout `AddressPicker` flow.

## Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Where: `DeliveryLocationPicker` modal + auto-set on login. | Frictionless first-load for logged-in customers; explicit switching via modal. |
| 2 | Auto-set fires only when `location === DEFAULT_DELIVERY_LOCATION`. | Preserves any pick a guest made before logging in. `AuthContext.logout` already clears `kb_delivery_location`, so the next login can auto-set again. |
| 3 | Modal layout: saved-address rows on top, autocomplete + map below a divider that reads "or pick a new location". | Linear scroll, no tab state, easy to scan. |
| 4 | Addresses without lat/lng are hidden from the list. | `DeliveryLocation` strictly needs coordinates; degraded rows would mislead. |
| 5 | Architecture: one `CustomerAddressesProvider` context fetches `/api/v1/customers/me` once; both the picker and the auto-sync component read it. | Single fetch source, reusable for future UI. |

## Architecture

### Files added

| File | Purpose |
|------|---------|
| `frontend/src/lib/CustomerAddressesContext.tsx` | Provider + `useCustomerAddresses` hook. Fetches `GET /api/v1/customers/me` once when conditions are met, exposes `addresses`, `defaultAddress`, `loading`, `error`, `refetch`. |
| `frontend/src/components/DeliveryLocationAutoSync.tsx` | Side-effect-only component. Mounted under the customer layout. Sets `DeliveryLocation` once when the customer logs in and the location is still the Mumbai fallback. |
| `frontend/src/components/DeliveryLocationPicker.module.css` (additions) | Styles for the saved-address rows section. |

### Files modified

| File | Change |
|------|--------|
| `frontend/src/lib/DeliveryLocationContext.tsx` | Add a `hydrated: boolean` flag that flips `true` once the initial `localStorage` read completes. Expose via context value. |
| `frontend/src/components/DeliveryLocationPicker.tsx` | Render new "Saved addresses" section above the existing autocomplete + map. Source data from `useCustomerAddresses`. |
| `frontend/src/app/(customer)/[locale]/layout.tsx` | Insert `<CustomerAddressesProvider>` between `<DeliveryLocationProvider>` and `<CartProvider>` (so the Navbar — which lives under `<CartProvider>` — can consume it), and mount `<DeliveryLocationAutoSync />` as the first child of `<CustomerAddressesProvider>` before `<CartProvider>`. Final tree: `AuthProvider → DeliveryLocationProvider → CustomerAddressesProvider → ( DeliveryLocationAutoSync, CartProvider → Navbar … )`. |

### Files left untouched

- `frontend/src/app/(operator)/layout.tsx` — operator routes (seller/admin) do not need auto-sync; they don't shop from their dashboards.
- `frontend/src/components/orders/AddressPicker.tsx` — checkout flow is store-scoped and already lists saved addresses.
- All backend code.

## Contracts

### `CustomerAddressesContext`

Reuses the existing `CustomerAddress` and `Address` types from `frontend/src/types/index.ts` (no new shape). The API response is the existing `CustomerProfile` shape from `GET /api/v1/customers/me`; the provider extracts `profile.addresses` and discards the rest.

```ts
import type { CustomerAddress } from "@/types";

interface CustomerAddressesContextValue {
  addresses: CustomerAddress[];           // full list as returned by API
  defaultAddress: CustomerAddress | null; // addresses.find(is_default) ?? null
  loading: boolean;                       // true while fetch in flight
  error: string | null;                   // last fetch error message
  refetch: () => void;                    // manual refresh hook
}
```

**Fetch gate:** the provider fetches only when `auth.loading === false && auth.token != null && auth.dbUser?.role === "customer"` (backend `UserRole.Customer` serializes to the string `"customer"`). Other states yield `{ addresses: [], defaultAddress: null, loading: false, error: null }`. The dependency array keys on `(token, role, auth.loading)`; a logout that flips `token` to `null` clears the list.

**Error handling:** fetch failure sets `error` and leaves `addresses = []`. No automatic retry; callers degrade gracefully.

### `DeliveryLocationContext` — new `hydrated` flag

```ts
interface DeliveryLocationContextValue {
  location: DeliveryLocation;
  hydrated: boolean;          // NEW — true after first localStorage read
  setLocation: (loc: DeliveryLocation | null) => void;
  clear: () => void;
}
```

`hydrated` starts `false`, flips to `true` at the end of the existing hydration `useEffect` (after the `setLocationState` call, whether or not a stored value was found). The storage listener does not touch `hydrated`.

### `DeliveryLocationAutoSync` behavior

```ts
function DeliveryLocationAutoSync() {
  const auth = useAuth();
  const { location, hydrated, setLocation } = useDeliveryLocation();
  const { defaultAddress, addresses, loading } = useCustomerAddresses();
  const didSyncRef = useRef(false);

  useEffect(() => {
    if (didSyncRef.current) return;
    if (auth.loading || !hydrated || loading) return;
    if (!auth.token || auth.dbUser?.role !== "customer") return;
    if (!isDefaultDeliveryLocation(location)) return;

    const target = pickAutoSyncAddress(defaultAddress, addresses);
    if (!target) return;

    setLocation({
      lat: target.address.latitude!,
      lng: target.address.longitude!,
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

  // Reset the one-shot when the auth identity changes so a second
  // customer signing in on the same tab also gets auto-synced.
  useEffect(() => {
    didSyncRef.current = false;
  }, [auth.token, auth.dbUser?.id]);

  return null;
}
```

`pickAutoSyncAddress(defaultAddress, addresses)` returns the default if it has both `latitude` and `longitude`, else the first address in `addresses` with both. Returns `null` if none qualify.

`isDefaultDeliveryLocation(loc)` is a new exported helper in `frontend/src/lib/DeliveryLocationContext.tsx`, next to `DEFAULT_DELIVERY_LOCATION`. It compares `lat`, `lng`, and `label` against `DEFAULT_DELIVERY_LOCATION` with strict equality. Float compare is safe because the values come from the constant; no arithmetic mutates them.

`pickAutoSyncAddress(defaultAddress, addresses)` is a local helper inside `DeliveryLocationAutoSync.tsx` (not exported).

### `DeliveryLocationPicker` — saved-address section

```
┌─────────────────────────────────────────────┐
│ Saved addresses                             │
│ ┌─────────────────────────────────────────┐ │
│ │ Home · Default                          │ │
│ │ Flat 12, Bandra W, Mumbai 400050        │ │
│ └─────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────┐ │
│ │ Office                                  │ │
│ │ 2nd Flr, BKC, Mumbai 400051             │ │
│ └─────────────────────────────────────────┘ │
│ ─────────── or pick a new location ──────── │
│ [autocomplete input]                        │
│ [map picker]                                │
└─────────────────────────────────────────────┘
```

Rules:
- Section is hidden when `auth.dbUser?.role !== "customer"`, when `addresses.length === 0`, or when every address lacks coordinates.
- Tapping a row sets `staged = { lat, lng, label: truncateLabel(formatAddress(...), 40) }` and does not touch `mapTarget` (the map keeps its existing position; the saved row is the source of truth on confirm).
- The confirm button uses the existing `staged` → `setLocation` path. No new state machine.
- Each row uses a `button` element with `type="button"`, full keyboard support. The default row carries a small "Default" pill (CSS `::after` or inline `<span>`).

## Data flow

### Manual pick

```
User taps "Deliver to" chip
  → DeliveryLocationPicker opens
  → useCustomerAddresses returns cached addresses
  → modal renders coord-bearing addresses as buttons
  → user taps row → staged = { lat, lng, label }
  → user taps "Confirm" → setLocation(staged) → modal closes
```

### Auto-sync on login

```
AuthContext.token transitions null → "jwt..."
  → CustomerAddressesProvider effect fires fetch
  → fetch resolves → addresses populated
  → DeliveryLocationAutoSync effect re-runs:
      auth.loading? no  hydrated? yes  loading? no
      token? yes  role==="customer"? yes
      location === DEFAULT? yes  target? yes
  → setLocation({ lat, lng, label }) once
  → didSyncRef = true
```

### Logout

```
AuthContext.logout()
  → clearStoredDeliveryLocation() runs (already in code)
  → DeliveryLocationProvider storage listener resets state to DEFAULT
  → token flips to null → CustomerAddressesProvider clears addresses
  → didSyncRef resets via the token-change effect
```

## Edge cases

| Case | Behavior |
|------|----------|
| Guest opens picker. | Saved section hidden; autocomplete + map only. |
| Logged in, zero addresses. | Saved section hidden. |
| All addresses lack coords. | Saved section hidden. Auto-sync no-ops. |
| Default lacks coords; another address has coords. | Picker renders the coord-bearing one. Auto-sync picks the same. |
| Hydration race: `localStorage` has a real value; auth resolves first. | AutoSync waits on `hydrated === true`, so it sees the stored value (not the fallback) and no-ops. |
| Guest set a location, then logs in. | Stored value ≠ fallback → AutoSync no-ops. Manual pick still works. |
| Customer logs in on tab A, then tab B. | `AuthContext` does not listen for cross-tab token changes, so tab B keeps its prior token state until reloaded. After a manual reload, tab B's mount-time hydration picks up the new token and AutoSync fires there too. Out of scope to add a token storage listener in this spec. |
| Network error fetching `/customers/me`. | Provider sets `error`, leaves list empty. Picker hides saved section. Modal still functional. |
| Customer adds a new default address while modal is open. | No live refresh; user reopens modal or refreshes. Acceptable for MVP. |
| Customer logs out then logs in as a different customer. | Token change effect resets `didSyncRef`. New addresses fetched. Auto-sync runs again if location is still fallback. |
| `setLocation` called by AutoSync triggers a re-render. | Loop guard: `isDefaultDeliveryLocation(location)` flips false after the set, plus `didSyncRef` is true; effect exits early. |

## Manual verification checklist

Frontend has no test runner per `CLAUDE.md`. Verify by running the dev stack:

1. **Guest path**: open the app without logging in, click the "Deliver to" chip → modal shows autocomplete + map only, no saved section.
2. **Logged-in customer with default**: log in, navbar chip updates to the default address city after `/customers/me` resolves.
3. **Tap a saved row**: open modal, tap a saved address row, confirm → modal closes, chip shows that address.
4. **Guest pick preserved**: as a guest, pick a Mumbai-adjacent location via the map, then log in → chip retains the guest pick (auto-sync no-ops).
5. **Logout resets**: log out → chip resets to "Mumbai, Maharashtra, India".
6. **Coordless filter**: temporarily edit a saved address to clear lat/lng (via account settings), open picker → that row does not appear; coord-bearing rows still render.
7. **Cross-tab logout**: open the app in two tabs, log out from tab A → tab B's chip resets and saved section disappears in tab B.
8. **Operator routes unaffected**: sign in as a seller, visit `/seller` → no `/customers/me` request fires, no auto-sync side effects.

## Risks

- **Double fetch on remount.** `CustomerAddressesProvider` uses local React state, so unmounting/remounting the customer layout (e.g., locale switch) refetches. Acceptable — locale switch is rare and the endpoint is cheap.
- **Float equality for fallback check.** Addressed by comparing against the literal `DEFAULT_DELIVERY_LOCATION` constant without intermediate math; the value is referentially stable.
- **Saved-row label truncation.** `truncateLabel(_, 40)` matches the chip width; longer human-readable text still appears inside the row's body, so the truncation only affects the chip.

## Out of scope (future work)

- "Save this pin" button inside the modal.
- Showing `Default` pill in the chip itself.
- Per-store serviceability hints next to saved rows (the modal is global, not store-scoped).
- Server-side `default_delivery_address_id` preference for cross-device persistence.
