# Checkout: Serviceable-Address Gating

**Status:** Draft
**Date:** 2026-05-11
**Scope:** Frontend only — `AddressPicker` + checkout page wiring + i18n.

## Problem

Checkout (`frontend/src/app/(customer)/[locale]/checkout/[storeId]/[serviceId]/page.tsx`)
lets the customer pick any saved address and click **Place Order**, even when
the address is outside the store's `delivery_radius_km`. The backend already
rejects out-of-radius orders via `ST_DWithin` in
`backend/app/src/app/services/checkout.py`, but the UI does not stop the
attempt — the customer fills the form, clicks the button, and discovers the
problem only after a server error.

Today's `AddressPicker` already calls `/api/v1/geo/serviceability` per address
and disables non-serviceable rows in the `<select>`, but four gaps remain:

1. The default address auto-selects on profile load *before* serviceability
   resolves, so a non-serviceable default sits pre-selected.
2. **Place Order** only checks `addressId === null` — it does not gate on
   serviceability.
3. No handling for "customer has saved addresses but none are serviceable for
   this store."
4. No loading state surfaced to the parent — the button is clickable while
   serviceability checks are still in flight.

## Goals

- The customer can only choose addresses inside this store's delivery radius.
- **Place Order** is disabled until a valid, in-radius address is actively
  selected — including for the default address.
- The customer gets a clear path forward when none of their saved addresses
  qualify ("add a new address").
- No backend changes. Server-side `ST_DWithin` remains the final authority.

## Non-Goals

- No retry UI for transient `/api/v1/geo/serviceability` failures. A network
  error continues to mark an address as non-serviceable. Revisit only if
  field reports show false negatives.
- No cross-navigation caching of serviceability results.
- No new entry point for `AddressPicker` — single caller (checkout page) only.

## Design

### Component: `AddressPicker` (`frontend/src/components/orders/AddressPicker.tsx`)

#### State

```ts
const [addresses, setAddresses] = useState<CustomerAddressApi[]>([]);
const [profileLoading, setProfileLoading] = useState(true);
const [serviceability, setServiceability] = useState<Record<number, boolean>>({});
const didAutoSelect = useRef(false);
```

`serviceability` is keyed by address id. An address id is *resolved* when it
appears as a key (value `true` or `false`). An address with null lat/lng
resolves to `false` immediately without a network call. **Storeless mode
(`storeId === undefined`) skips serviceability entirely and treats every
address as serviceable** — preserves the existing optional-prop contract.

The "all settled" predicate:

```ts
const allSettled =
  !profileLoading &&
  (storeId === undefined || addresses.every((a) => a.id in serviceability));
```

#### Serviceability fetch

Replace the sequential `for...of` loop with a parallel resolution:

```ts
useEffect(() => {
  if (storeId === undefined || addresses.length === 0) return;
  let cancelled = false;

  const checks = addresses.map(async (a) => {
    if (a.address.latitude == null || a.address.longitude == null) {
      return [a.id, false] as const;
    }
    try {
      const r = await checkServiceability(
        a.address.latitude, a.address.longitude, storeId,
      );
      return [a.id, r.serviceable] as const;
    } catch {
      return [a.id, false] as const;
    }
  });

  Promise.all(checks).then((entries) => {
    if (cancelled) return;
    setServiceability(Object.fromEntries(entries));
  });

  return () => { cancelled = true; };
}, [addresses, storeId]);
```

Batch-write the final map only after all results land — avoids partial
re-renders that would briefly mark resolved addresses as non-serviceable
during the loading window.

#### Default-selection rules

A separate effect, gated by `allSettled` and `didAutoSelect.current === false`:

```ts
useEffect(() => {
  if (!allSettled) return;
  if (didAutoSelect.current) return;
  if (value !== null) { didAutoSelect.current = true; return; }
  if (addresses.length === 0) { didAutoSelect.current = true; return; }

  const isOk = (id: number) =>
    storeId === undefined || serviceability[id] === true;

  const def = addresses.find((a) => a.is_default);
  const pick =
    (def && isOk(def.id) ? def : null) ??
    addresses.find((a) => isOk(a.id)) ??
    null;

  if (pick) onChange(pick.id);
  didAutoSelect.current = true;
}, [allSettled, addresses, serviceability, storeId, value, onChange]);
```

The `didAutoSelect` ref guarantees the auto-pick fires at most once per mount.
If the customer later changes `value` and then deselects to `null`, the
component does **not** re-auto-select — by design, the customer is in control
after first interaction.

#### Parent contract — `onStateChange`

Replace the existing `onSelectedAddress` prop with a single state callback
that always fires (no `null` payload):

```ts
interface PickerState {
  selectedId: number | null;
  latitude: number | null;
  longitude: number | null;
  serviceable: boolean;   // true when storeId undefined OR picked id is in-radius
  loading: boolean;        // true while profile or serviceability unresolved
}

interface Props {
  value: number | null;
  onChange: (id: number) => void;
  storeId?: number;
  onStateChange?: (state: PickerState) => void;
}
```

`loading` covers both pre-resolution and zero-serviceable states *with no
selection yet*, so the checkout page can use a single flag for its button.

#### Zero-serviceable empty state

When `allSettled === true`, `addresses.length > 0`, and no entry in
`serviceability` is `true`, render the existing `.empty` block with new copy:

```tsx
<div className={styles.empty}>
  {t("noServiceableTitle")}{" "}
  <Link href="/account/settings" className={styles.link}>{t("pickerAddOne")}</Link>
</div>
```

No `<select>` is rendered in this state. `onChange` is never called from the
component in this branch.

#### Dropdown rendering (unchanged behavior)

Non-serviceable addresses remain visible as disabled `<option>` rows with the
existing "(Outside delivery area)" suffix. Keeps the customer's mental model
of their saved addresses intact.

### Checkout page (`frontend/src/app/(customer)/[locale]/checkout/[storeId]/[serviceId]/page.tsx`)

#### State

Replace the existing `selectedAddress` state with the new picker state:

```ts
const [pickerState, setPickerState] = useState<PickerState>({
  selectedId: null,
  latitude: null,
  longitude: null,
  serviceable: false,
  loading: true,
});
```

#### Place Order gating

```ts
const canPlace =
  !submitting &&
  pickerState.selectedId !== null &&
  !pickerState.loading &&
  pickerState.serviceable;
```

Button:

```tsx
<button
  className={styles.placeBtn}
  onClick={onPlaceOrder}
  disabled={!canPlace}
>
  {submitting
    ? t("placing")
    : pickerState.loading
      ? t("checkingDeliveryArea")
      : t("placeOrder", { total })}
</button>
```

`onPlaceOrder` reads `pickerState.selectedId` rather than the removed
`addressId` state.

#### Route map

The existing `<DeliveryRouteMap>` block, currently gated by
`selectedAddress?.serviceable && latitude/longitude present`, switches to
`pickerState.serviceable && pickerState.latitude/longitude` — same semantics,
new field source.

### i18n

Add one key per locale to the existing `Address` and `Checkout` namespaces.
All five files: `en.json`, `hi.json`, `mr.json`, `gu.json`, `pa.json`.

- `Address.noServiceableTitle` — "No saved address is within this store's delivery area." (English; translate per locale, following the tone of neighboring keys in each file)
- `Checkout.checkingDeliveryArea` — "Checking delivery area…" (English; translate per locale)

Reuse the existing `Address.pickerAddOne` for the link copy in the new state —
no new key needed there.

## Edge Cases

| Case | Behavior |
|------|----------|
| Customer has zero saved addresses | Existing `pickerEmpty` block (unchanged). Button stays disabled (no selection). |
| Default address is serviceable | Auto-selected. Button enabled once `loading=false`. |
| Default is non-serviceable, others serviceable | Default skipped, first serviceable auto-selected. |
| No address is serviceable | New empty-state copy rendered. Button stays disabled. |
| All addresses lack lat/lng | Equivalent to "no serviceable" — new empty-state. (lat/lng missing → marked non-serviceable.) |
| Customer manually picks a disabled option | Cannot — native `<option disabled>` blocks selection. |
| Serviceability network error | Address marked non-serviceable. No retry surfaced. |
| `storeId` undefined (storeless mode) | No serviceability calls. All addresses treated as serviceable. Existing callers (none today) preserved. |
| Customer changes address after auto-pick | `didAutoSelect` ref prevents the effect from overriding; standard `onChange` flow takes over. |

## Error Handling

- `/api/v1/customers/me` failure: existing behavior — `loading` flips off, the
  picker shows an empty state. No new path.
- `/api/v1/geo/serviceability` failure (per address): caught, mapped to
  `false`. Customer sees the address as disabled. Backend still re-validates
  on submit — the safety net.
- Server-side `ST_DWithin` rejection at order creation: unchanged. Existing
  error toast / message in `onPlaceOrder` catches it. With this design,
  reaching that branch should require a race (radius shrunk mid-checkout).

## Testing

No frontend tests in this repo (per `CLAUDE.md`). Manual verification
checklist for the implementer:

1. **Default serviceable** — load checkout with a default address inside
   radius. Default pre-selected, button enabled after spinner.
2. **Default non-serviceable, alternate serviceable** — set a non-serviceable
   default, add a serviceable second address. Reload checkout. Second address
   auto-selected, button enabled.
3. **No serviceable addresses** — all addresses outside radius. Reload
   checkout. Empty-state copy shown with "Add one" link to
   `/account/settings`. Button disabled.
4. **Loading window** — throttle network to slow 3G. Confirm button shows
   "Checking delivery area…" and is disabled until checks resolve.
5. **Address with null lat/lng** — saved before geocoding was wired (legacy
   data). Marked non-serviceable; same treatment as out-of-radius.
6. **Backend safety net** — admin reduces `delivery_radius_km` mid-checkout
   (or move the store pin). Submit. Backend `ST_DWithin` rejection still
   surfaces as an error toast.

Backend coverage for `ST_DWithin` enforcement remains in
`backend/app/tests/` (per `docs/superpowers/specs/2026-05-06-geo-stores-delivery-radius-design.md`).

## Rollout

- Single PR. No feature flag — the UI tightens behavior the backend already
  enforces; no migration concerns.
- Branch: `feat/checkout-serviceable-address-gating`.
- Conventional Commits scope: `checkout`.

## Files Touched

| File | Change |
|------|--------|
| `frontend/src/components/orders/AddressPicker.tsx` | State refactor, parallel serviceability, `onStateChange` callback, zero-serviceable empty state, `didAutoSelect` ref. |
| `frontend/src/app/(customer)/[locale]/checkout/[storeId]/[serviceId]/page.tsx` | Replace `selectedAddress` with `pickerState`. New button gating logic + label. Update `<DeliveryRouteMap>` field references. |
| `frontend/messages/{en,hi,mr,gu,pa}.json` | Add `Address.noServiceableTitle` + `Checkout.checkingDeliveryArea`. |

No new files. No new dependencies.
