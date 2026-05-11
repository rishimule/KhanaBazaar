# Checkout Serviceable-Address Gating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restrict checkout address selection to addresses inside the store's delivery radius and disable Place Order until a valid in-radius address is actively selected.

**Architecture:** Frontend-only change. `AddressPicker` already calls `/api/v1/geo/serviceability` per saved address — this plan tightens its behavior (parallel checks, `didAutoSelect` ref, zero-serviceable empty state) and replaces its `onSelectedAddress` callback with an always-firing `onStateChange` callback. The checkout page consumes the new callback to gate the Place Order button on `selectedId !== null && !loading && serviceable`. Backend `ST_DWithin` enforcement is unchanged and remains the source of truth.

**Tech Stack:** Next.js 16.1 (App Router), React 19.2, TypeScript 5, CSS Modules, `next-intl` (5 locales: en/hi/mr/gu/pa). No frontend test framework in repo — verification is `npm run lint` + `npx tsc --noEmit` + manual checklist from the spec.

**Spec:** `docs/superpowers/specs/2026-05-11-checkout-serviceable-address-gating-design.md`

---

## File Map

| File | Change |
|------|--------|
| `frontend/messages/en.json` | Add `Address.noServiceableTitle` + `Checkout.checkingDeliveryArea` |
| `frontend/messages/hi.json` | Same (Hindi translations) |
| `frontend/messages/mr.json` | Same (Marathi translations) |
| `frontend/messages/gu.json` | Same (Gujarati translations) |
| `frontend/messages/pa.json` | Same (Punjabi translations) |
| `frontend/src/components/orders/AddressPicker.tsx` | Parallel serviceability fetch, `onStateChange` callback contract, `didAutoSelect` ref, zero-serviceable empty state |
| `frontend/src/app/(customer)/[locale]/checkout/[storeId]/[serviceId]/page.tsx` | Replace `selectedAddress` state with `pickerState`; gate Place Order button on loading + serviceable; update button label and route-map field references |

No new files. No new dependencies.

---

## Task 1: Add i18n keys to all five locale files

**Files:**
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/hi.json`
- Modify: `frontend/messages/mr.json`
- Modify: `frontend/messages/gu.json`
- Modify: `frontend/messages/pa.json`

This task is independent — keys can ship even before consumers exist. Each
file gets two new keys: `Checkout.checkingDeliveryArea` and
`Address.noServiceableTitle`.

- [ ] **Step 1: Add the `Checkout.checkingDeliveryArea` key to `en.json`**

In `frontend/messages/en.json`, locate the `Checkout` block (around line 102).
Add the new key immediately after `placing`:

```json
"placing": "Placing order…",
"checkingDeliveryArea": "Checking delivery area…",
"placeOrder": "Place Order — ₹{total}"
```

- [ ] **Step 2: Add the `Address.noServiceableTitle` key to `en.json`**

In the same file, locate the `Address` block (around line 263). Add the new
key immediately after `pickerEmpty`:

```json
"pickerEmpty": "No saved address.",
"noServiceableTitle": "No saved address is within this store's delivery area.",
"pickerAddOne": "Add one",
```

- [ ] **Step 3: Add the same two keys to `hi.json` (Hindi)**

Add to `Checkout` after `placing`:
```json
"checkingDeliveryArea": "डिलीवरी क्षेत्र की जाँच हो रही है…",
```

Add to `Address` after `pickerEmpty`:
```json
"noServiceableTitle": "इस स्टोर के डिलीवरी क्षेत्र में कोई सहेजा गया पता नहीं है।",
```

- [ ] **Step 4: Add the same two keys to `mr.json` (Marathi)**

Add to `Checkout` after `placing`:
```json
"checkingDeliveryArea": "वितरण क्षेत्र तपासत आहोत…",
```

Add to `Address` after `pickerEmpty`:
```json
"noServiceableTitle": "या दुकानाच्या वितरण क्षेत्रात कोणताही जतन केलेला पत्ता नाही.",
```

- [ ] **Step 5: Add the same two keys to `gu.json` (Gujarati)**

Add to `Checkout` after `placing`:
```json
"checkingDeliveryArea": "ડિલિવરી વિસ્તાર તપાસી રહ્યાં છીએ…",
```

Add to `Address` after `pickerEmpty`:
```json
"noServiceableTitle": "આ સ્ટોરના ડિલિવરી વિસ્તારમાં કોઈ સાચવેલ સરનામું નથી.",
```

- [ ] **Step 6: Add the same two keys to `pa.json` (Punjabi)**

Add to `Checkout` after `placing`:
```json
"checkingDeliveryArea": "ਡਿਲੀਵਰੀ ਖੇਤਰ ਜਾਂਚ ਰਹੇ ਹਾਂ…",
```

Add to `Address` after `pickerEmpty`:
```json
"noServiceableTitle": "ਇਸ ਸਟੋਰ ਦੇ ਡਿਲੀਵਰੀ ਖੇਤਰ ਵਿੱਚ ਕੋਈ ਸੰਭਾਲਿਆ ਪਤਾ ਨਹੀਂ ਹੈ।",
```

- [ ] **Step 7: Verify JSON validity**

Run from repo root:
```bash
for f in frontend/messages/*.json; do echo "--- $f"; node -e "JSON.parse(require('fs').readFileSync('$f','utf8'))" && echo "ok"; done
```
Expected: each line ends with `ok`. If any throws, fix the trailing-comma or quote issue before continuing.

- [ ] **Step 8: Commit**

```bash
git add frontend/messages/en.json frontend/messages/hi.json frontend/messages/mr.json frontend/messages/gu.json frontend/messages/pa.json
git commit -m "feat(checkout): add i18n keys for serviceable-address gating"
```

---

## Task 2: Convert AddressPicker's serviceability fetch to parallel resolution

**Files:**
- Modify: `frontend/src/components/orders/AddressPicker.tsx:74-96`

Behavior-preserving refactor: replace the sequential `for...of` `await` loop
with `Promise.all`. Same result, no UI-visible difference, sets up Task 4.

- [ ] **Step 1: Replace the sequential serviceability effect**

In `frontend/src/components/orders/AddressPicker.tsx`, locate the effect at
lines 74–96 (starts with `useEffect(() => { if (storeId === undefined ...`).
Replace the whole `useEffect` block with:

```tsx
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

- [ ] **Step 2: Type-check**

Run from `frontend/`:
```bash
npx tsc --noEmit
```
Expected: exit 0, no errors.

- [ ] **Step 3: Lint**

Run from `frontend/`:
```bash
npm run lint
```
Expected: exit 0, no errors. If ESLint reports unused imports or hooks-deps warnings, fix them inline before continuing.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/orders/AddressPicker.tsx
git commit -m "refactor(checkout): parallelize address serviceability checks"
```

---

## Task 3: Replace `onSelectedAddress` with `onStateChange` and wire checkout button

**Files:**
- Modify: `frontend/src/components/orders/AddressPicker.tsx` (props interface + selection-emit effect)
- Modify: `frontend/src/app/(customer)/[locale]/checkout/[storeId]/[serviceId]/page.tsx` (state + button gating)

The new contract bundles loading + serviceable flags into a single state
object that ALWAYS fires (never `null`). The checkout page reads `loading`
and `serviceable` directly off this object to gate the button. Single caller
of `AddressPicker` exists, so the prop rename is a clean breaking change.

- [ ] **Step 1: Replace the `Props` interface and exported `PickerState` type**

In `frontend/src/components/orders/AddressPicker.tsx`, replace the `Props`
interface block (currently around lines 34–49) with:

```tsx
export interface PickerState {
  selectedId: number | null;
  latitude: number | null;
  longitude: number | null;
  /** True when storeId is undefined OR the picked address is in-radius. */
  serviceable: boolean;
  /** True while profile is loading OR any serviceability check unresolved. */
  loading: boolean;
}

interface Props {
  value: number | null;
  onChange: (id: number) => void;
  /** When set, each saved address is checked against this store's delivery
   *  radius via /api/v1/geo/serviceability and disabled if outside. */
  storeId?: number;
  /** Fires whenever the picker's effective state changes. Always called
   *  (never null) so parents can gate on `loading` even before a selection
   *  exists (e.g. zero-serviceable). */
  onStateChange?: (state: PickerState) => void;
}
```

- [ ] **Step 2: Rename the destructured prop in the component signature**

In the same file, change the component signature (currently around lines
51–53) from:

```tsx
export default function AddressPicker({
  value, onChange, storeId, onSelectedAddress,
}: Props) {
```

to:

```tsx
export default function AddressPicker({
  value, onChange, storeId, onStateChange,
}: Props) {
```

- [ ] **Step 3: Rename the profile-loading state for clarity**

In the same file, change:

```tsx
  const [loading, setLoading] = useState(true);
```

to:

```tsx
  const [profileLoading, setProfileLoading] = useState(true);
```

Then update the profile-fetch effect's `.finally(() => setLoading(false))` to
`.finally(() => setProfileLoading(false))`, and update the early-return
`if (loading) return ...` line to `if (profileLoading) return ...`.

- [ ] **Step 4: Replace the selection-emit effect with state-emit effect**

In the same file, locate the `useEffect` that previously called
`onSelectedAddress(...)` (around lines 100–117). Replace the whole block with:

```tsx
  const allSettled =
    !profileLoading &&
    (storeId === undefined || addresses.every((a) => a.id in serviceability));

  useEffect(() => {
    if (!onStateChange) return;
    const picked = value != null ? addresses.find((a) => a.id === value) : undefined;
    onStateChange({
      selectedId: picked?.id ?? null,
      latitude: picked?.address.latitude ?? null,
      longitude: picked?.address.longitude ?? null,
      serviceable:
        picked === undefined
          ? false
          : storeId === undefined
            ? true
            : serviceability[picked.id] === true,
      loading: !allSettled,
    });
  }, [value, addresses, serviceability, storeId, allSettled, onStateChange]);
```

- [ ] **Step 5: Update checkout page state shape and import**

In `frontend/src/app/(customer)/[locale]/checkout/[storeId]/[serviceId]/page.tsx`,
change the `AddressPicker` import line (line 14) from:

```tsx
import AddressPicker from "@/components/orders/AddressPicker";
```

to:

```tsx
import AddressPicker, { type PickerState } from "@/components/orders/AddressPicker";
```

Then replace the existing state declaration (lines 30–36):

```tsx
  const [addressId, setAddressId] = useState<number | null>(null);
  const [selectedAddress, setSelectedAddress] = useState<{
    id: number;
    latitude: number | null;
    longitude: number | null;
    serviceable: boolean;
  } | null>(null);
```

with:

```tsx
  const [addressId, setAddressId] = useState<number | null>(null);
  const [pickerState, setPickerState] = useState<PickerState>({
    selectedId: null,
    latitude: null,
    longitude: null,
    serviceable: false,
    loading: true,
  });
```

- [ ] **Step 6: Update the `<AddressPicker>` JSX usage**

In the same file, replace the existing `<AddressPicker ... />` block (lines
183–188) with:

```tsx
          <AddressPicker
            value={addressId}
            onChange={setAddressId}
            storeId={storeId}
            onStateChange={setPickerState}
          />
```

- [ ] **Step 7: Update the `<DeliveryRouteMap>` block to read from `pickerState`**

In the same file, replace the existing conditional render (lines 189–208):

```tsx
          {selectedAddress?.serviceable &&
            selectedAddress.latitude != null &&
            selectedAddress.longitude != null &&
            storeDetails?.address.latitude != null &&
            storeDetails?.address.longitude != null && (
              <div className={styles.routeMap}>
                <DeliveryRouteMap
                  store={{
                    lat: storeDetails.address.latitude,
                    lng: storeDetails.address.longitude,
                    label: storeDetails.name,
                  }}
                  customer={{
                    lat: selectedAddress.latitude,
                    lng: selectedAddress.longitude,
                    label: "Your address",
                  }}
                />
              </div>
            )}
```

with:

```tsx
          {pickerState.serviceable &&
            pickerState.latitude != null &&
            pickerState.longitude != null &&
            storeDetails?.address.latitude != null &&
            storeDetails?.address.longitude != null && (
              <div className={styles.routeMap}>
                <DeliveryRouteMap
                  store={{
                    lat: storeDetails.address.latitude,
                    lng: storeDetails.address.longitude,
                    label: storeDetails.name,
                  }}
                  customer={{
                    lat: pickerState.latitude,
                    lng: pickerState.longitude,
                    label: "Your address",
                  }}
                />
              </div>
            )}
```

- [ ] **Step 8: Update the Place Order button gating**

In the same file, replace the existing button block (lines 239–245):

```tsx
        <button
          className={styles.placeBtn}
          onClick={onPlaceOrder}
          disabled={submitting || addressId === null}
        >
          {submitting ? t("placing") : t("placeOrder", { total })}
        </button>
```

with:

```tsx
        <button
          className={styles.placeBtn}
          onClick={onPlaceOrder}
          disabled={
            submitting ||
            pickerState.selectedId === null ||
            pickerState.loading ||
            !pickerState.serviceable
          }
        >
          {submitting
            ? t("placing")
            : pickerState.loading
              ? t("checkingDeliveryArea")
              : t("placeOrder", { total })}
        </button>
```

- [ ] **Step 9: Type-check and lint**

Run from `frontend/`:
```bash
npx tsc --noEmit && npm run lint
```
Expected: both exit 0.

If TypeScript complains about an unused `selectedAddress` reference elsewhere
in the file, search for it and remove. The only reads should be the ones
replaced in Steps 5–7.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/orders/AddressPicker.tsx frontend/src/app/(customer)/[locale]/checkout/[storeId]/[serviceId]/page.tsx
git commit -m "feat(checkout): gate Place Order on address serviceability"
```

---

## Task 4: Defer default-pick with `didAutoSelect` ref

**Files:**
- Modify: `frontend/src/components/orders/AddressPicker.tsx` (profile-fetch effect + new auto-select effect)

The current profile-fetch effect auto-selects the default address inline,
*before* serviceability resolves. Split that responsibility: profile fetch
just loads addresses; a separate effect — gated on `allSettled` and a
`didAutoSelect` ref — picks the first serviceable address.

- [ ] **Step 1: Import `useRef`**

In `frontend/src/components/orders/AddressPicker.tsx`, update the React import
at line 5 from:

```tsx
import { useEffect, useState } from "react";
```

to:

```tsx
import { useEffect, useRef, useState } from "react";
```

- [ ] **Step 2: Add the `didAutoSelect` ref**

In the same file, immediately after the `serviceability` state declaration,
add:

```tsx
  const didAutoSelect = useRef(false);
```

- [ ] **Step 3: Strip auto-select out of the profile-fetch effect**

Replace the profile-fetch effect (currently around lines 61–72) with:

```tsx
  useEffect(() => {
    if (!token) return;
    get<CustomerProfileResponse>("/api/v1/customers/me", token)
      .then((data) => { setAddresses(data.addresses); })
      .finally(() => setProfileLoading(false));
  }, [token]);
```

Note: `value` and `onChange` are removed from dep array — they were only used
for the auto-select branch we're moving.

- [ ] **Step 4: Add a separate auto-select effect**

Add the following effect immediately AFTER the serviceability-fetch effect
(the one updated in Task 2) and BEFORE the state-emit effect (the one added
in Task 3 Step 4):

```tsx
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

- [ ] **Step 5: Type-check and lint**

Run from `frontend/`:
```bash
npx tsc --noEmit && npm run lint
```
Expected: both exit 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/orders/AddressPicker.tsx
git commit -m "feat(checkout): defer default address pick until serviceability resolves"
```

---

## Task 5: Render zero-serviceable empty state

**Files:**
- Modify: `frontend/src/components/orders/AddressPicker.tsx` (render section)

When all serviceability checks resolve and no address is serviceable, replace
the `<select>` dropdown with an empty-state block linking to
`/account/settings`, mirroring the existing "no saved address" empty state.

- [ ] **Step 1: Add the zero-serviceable branch before the `<select>`**

In `frontend/src/components/orders/AddressPicker.tsx`, locate the render
section. Currently after the `addresses.length === 0` branch (around lines
120–127) and before the `isDisabled` helper.

Insert this block immediately AFTER the existing `addresses.length === 0`
early-return and BEFORE the `const isDisabled = ...` line:

```tsx
  const hasAnyServiceable =
    storeId === undefined ||
    addresses.some((a) => serviceability[a.id] === true);

  if (allSettled && !hasAnyServiceable) {
    return (
      <div className={styles.empty}>
        {t("noServiceableTitle")}{" "}
        <Link href="/account/settings" className={styles.link}>{t("pickerAddOne")}</Link>
      </div>
    );
  }
```

The existing `addresses.length === 0` block already handles the
no-addresses-at-all case; this new branch covers the
has-addresses-but-none-serviceable case.

- [ ] **Step 2: Type-check and lint**

Run from `frontend/`:
```bash
npx tsc --noEmit && npm run lint
```
Expected: both exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/orders/AddressPicker.tsx
git commit -m "feat(checkout): show empty state when no saved address is serviceable"
```

---

## Task 6: Build, manual verification, push, open PR

**Files:** No new edits. Verification + delivery only.

- [ ] **Step 1: Full production build**

Run from `frontend/`:
```bash
npm run build
```
Expected: exit 0, no errors. Build catches type + lint issues missed by
incremental checks.

- [ ] **Step 2: Start dev stack**

Run from repo root:
```bash
./scripts/dev.sh start
```
Wait until backend + frontend report ready in the script output.

- [ ] **Step 3: Manual checklist — default address inside radius**

Pre-condition: log in as a customer whose default address is geocoded and
inside the store's `delivery_radius_km`.

1. Add an item to the cart for that store.
2. Navigate to `/cart`, click Checkout for that store+service.
3. Confirm: button briefly reads "Checking delivery area…" then "Place Order — ₹{total}".
4. Default address is pre-selected.
5. Click Place Order. Order is created.

- [ ] **Step 4: Manual checklist — default non-serviceable, alternate serviceable**

Pre-condition: customer has at least two saved addresses — default outside
the store's radius, secondary inside.

1. Add cart item for the store, navigate to checkout.
2. Confirm: after "Checking delivery area…" resolves, the secondary
   (in-radius) address is the one auto-selected.
3. Default address still appears in the dropdown but marked
   "(Outside delivery area)" and is disabled.
4. Button enabled. Place order succeeds.

- [ ] **Step 5: Manual checklist — zero serviceable addresses**

Pre-condition: every saved address is outside the store's radius (or move the
store's pin in the seller dashboard / shrink `delivery_radius_km` to force
this).

1. Navigate to checkout.
2. Confirm: after "Checking delivery area…" resolves, the dropdown is
   replaced with the message
   "No saved address is within this store's delivery area. Add one"
   (with "Add one" linking to `/account/settings`).
3. Button remains disabled and reads "Place Order — ₹{total}".

- [ ] **Step 6: Manual checklist — loading window**

Pre-condition: any setup with at least one serviceable address.

1. In Chrome DevTools → Network, enable "Slow 3G" throttling.
2. Reload `/checkout/<storeId>/<serviceId>`.
3. Confirm: Place Order button reads "Checking delivery area…" and is
   disabled for the duration of the network round-trip.
4. After resolution, label reverts to "Place Order — ₹{total}" and the
   button enables.

- [ ] **Step 7: Manual checklist — address with null lat/lng**

Pre-condition: insert (or edit in the DB) one customer address with
`latitude IS NULL`.

1. Navigate to checkout.
2. Confirm: the null-coord address is marked "(Outside delivery area)" and
   disabled. Same as an out-of-radius address.

- [ ] **Step 8: Manual checklist — backend safety net**

1. Pick a serviceable address and reach checkout.
2. In another tab as the seller, shrink the store's `delivery_radius_km` so
   the picked address is now outside.
3. Click Place Order in the customer tab.
4. Confirm: backend rejects via `ST_DWithin`, and the existing error toast /
   error block surfaces the rejection. Customer is not redirected unless
   the error key is `service_unavailable` / `service_mismatch` (existing
   behavior).

- [ ] **Step 9: Storeless-mode regression check (smoke only)**

Search the repo for additional `AddressPicker` callers:

```bash
grep -rn "AddressPicker" frontend/src --include="*.tsx" --include="*.ts" | grep -v "AddressPicker.tsx\|AddressPicker.module"
```
Expected: only the checkout page. If anything else surfaces, audit it: a
storeless caller (no `storeId` prop) must still load addresses and emit a
state with `loading: false`, `serviceable: true` for the picked id, and no
empty-state regression.

- [ ] **Step 10: Push branch**

```bash
git push -u origin feat/checkout-serviceable-address-gating
```

- [ ] **Step 11: Open PR (only after the user explicitly approves)**

Per `CLAUDE.md`: wait for explicit user approval before opening a PR. When
approved, run:

```bash
gh pr create --title "feat(checkout): gate Place Order on address serviceability" --body "$(cat <<'EOF'
## Summary
- Restrict checkout address selection to addresses inside the store's delivery radius (no manual pick of disabled rows; auto-select skips a non-serviceable default).
- Disable Place Order until a valid in-radius address is actively selected (covers loading window, zero-serviceable state, and non-serviceable selection).
- New empty state when the customer has saved addresses but none are within the store's radius — links to /account/settings.

## Spec
docs/superpowers/specs/2026-05-11-checkout-serviceable-address-gating-design.md

## Test plan
- [ ] Default address inside radius → auto-selected, Place Order works.
- [ ] Default outside radius, alternate inside → alternate auto-selected.
- [ ] All addresses outside radius → empty-state shown, button disabled.
- [ ] Throttled network → button shows "Checking delivery area…" until checks resolve.
- [ ] Address with null lat/lng → treated as non-serviceable.
- [ ] Backend ST_DWithin rejection still surfaces error toast.
EOF
)"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Implementing task |
|--------------|-------------------|
| Default-selection rules (auto-pick first serviceable) | Task 4 |
| Place Order disabled until valid in-radius selection | Task 3 Step 8 |
| Zero-serviceable empty state with "Add one" CTA | Task 5 |
| Loading state — button reads "Checking delivery area…" | Task 1 + Task 3 Step 8 |
| Non-serviceable addresses still visible (disabled) | Existing behavior — preserved (Task 5 only adds the empty-state branch; the `<select>` rendering and `isDisabled` helper are untouched) |
| `onStateChange` callback contract | Task 3 Steps 1–4 |
| Parallel serviceability fetch | Task 2 |
| `didAutoSelect` ref to prevent re-selection loops | Task 4 |
| Storeless mode preserved | Task 3 Step 4 (`storeId === undefined` short-circuits to `serviceable: true`); Task 4 Step 4 (`isOk` returns `true` when `storeId === undefined`); Task 5 Step 1 (`hasAnyServiceable` short-circuits to `true`) |
| i18n keys in all 5 locale files | Task 1 |
| Backend changes | None — Task 6 Step 8 verifies the `ST_DWithin` safety net still fires |

No spec gaps.

**Placeholder scan:** No TBD/TODO/"fill-in" placeholders. Every code step has
the exact code an engineer pastes. Every command has expected output.

**Type consistency:** `PickerState` interface defined in Task 3 Step 1 is
imported and used identically in Task 3 Step 5 (`useState<PickerState>`) and
the button-gating block (Task 3 Step 8). Field names — `selectedId`,
`latitude`, `longitude`, `serviceable`, `loading` — match across all tasks
and the spec.

---

Plan complete and saved to `docs/superpowers/plans/2026-05-11-checkout-serviceable-address-gating.md`.
