# Checkout — Add Address Inline

**Date:** 2026-05-20
**Scope:** Frontend only (no backend changes)
**Touches:** `frontend/src/components/orders/AddressPicker.tsx`, `frontend/src/components/orders/AddressPicker.module.css`, `frontend/messages/*.json`

## Problem

On `/checkout/[storeId]/[serviceId]`, the address picker (`AddressPicker.tsx`) renders only a `<select>` of the customer's saved addresses. If a customer's target delivery address is not in that list, there is no path to add one without leaving checkout. The empty-state link points to `/account/settings`, which redirects to `/account/profile` — a page with no address management. The real management page is `/account/addresses`, but bouncing the customer out of a high-intent checkout flow risks abandonment.

## Goal

Let a customer add a new delivery address from inside the checkout page, in a modal, without leaving the flow. After save, the newly added address is auto-selected. Serviceability against the current store is re-checked using the picker's existing flow, so an out-of-radius new address remains gated by the existing place-order disable rule.

## Non-goals

- Editing or deleting addresses from checkout (still done on `/account/addresses`).
- Changing the navbar `DeliveryLocationPicker` (already has its own redirect-style Add address button).
- Backend changes — `POST /api/v1/customers/me/addresses` already exists and returns the full `CustomerProfile`.
- Automated tests — project has no frontend tests; verification is manual.

## UI

- New `+ Add address` outline button rendered on the same row as the `Deliver to` label, right-aligned. Visible whenever `AddressPicker` shows the dropdown (after profile fetch resolves).
- Both empty-state branches (`pickerEmpty`, `noServiceableTitle`) replace their current `<Link href="/account/settings">` with the same Add-Address button. The stale `/account/settings` link is removed.
- Clicking the button opens a `<Modal>` (using `frontend/src/components/Modal.tsx`, `size="wide"`) titled "Add delivery address". Modal body contains the same form fields used by `/account/addresses`:
  - Optional label input (e.g. "Home", "Work").
  - "Use current location" outline button — reverse-geocodes via `/api/v1/geo/reverse` and populates AddressFields.
  - `<AddressFields>` (line1 / line2 / city / state / pincode / country + lat/lng map pin via `MapPicker`).
  - "Make default" checkbox.
  - Footer: Cancel + Save Address.

## State + data flow

Modal state lives **inside** `AddressPicker` (not the checkout page) so the checkout page does not grow. New local state:

- `addModalOpen: boolean`
- `addForm: { label: string; is_default: boolean; address: Address }` (default = `emptyAddress()` from `@/components/AddressFields`)
- `saving: boolean`
- `geolocating: boolean`
- `addErrors: AddressFieldsErrors`
- `modalError: string | null`

On save:

1. Capture `prevIds = new Set(addresses.map(a => a.id))` before POST.
2. `POST /api/v1/customers/me/addresses` with `{ label, is_default, address }` (token from `useAuth()`).
3. On success:
   - Compute `newId = next.addresses.find(a => !prevIds.has(a.id))?.id`. (Server returns the full updated `CustomerProfile`; diff identifies the row this client just added.)
   - `setAddresses(next.addresses)`.
   - If `newId != null`, `onChange(newId)` — bypasses the `didAutoSelect.current` gate intentionally; the user chose to add this address, so we promote it immediately.
   - **Do not touch `didAutoSelect.current`.** It is already `true` after first auto-select; leaving it true keeps the gate closed for any future renders.
   - Close modal, reset form state.
4. On 422: parse via `validationErrorsForPrefix(error, "address")` (same helper pattern as the addresses page) into `addErrors`. Modal stays open.
5. On other errors: `apiErrorKey` lookup → `Errors.*` translation; fallback to a generic save-failed string. Modal stays open.

The existing `useEffect` that resolves serviceability (line 74-98 in current `AddressPicker.tsx`) re-runs on `addresses` array change, including the new id. Until it resolves, `allSettled` becomes false → `onStateChange` emits `loading: true`. The checkout page's place-order button already disables on `pickerState.loading`, so the user gets the existing "Checking delivery area" copy until the new address's serviceability is known. No additional gating needed.

If the new address is outside the store's delivery radius, the standard `(Outside delivery area)` suffix renders on the option and the option is disabled. The customer either picks a different saved address or opens the modal again to enter a different one.

## Translation strategy

The `/account/addresses` page already has all the form-related strings under the `Account.addresses.*` namespace in all 5 locales (en, hi, mr, gu, pa). `AddressPicker` currently uses the `Address.*` namespace.

Reuse `Account.addresses.*` keys from `AddressPicker` for the modal contents to avoid duplicating translations: `addAddress`, `addAddressFormTitle`, `cancel`, `saveAddress`, `saving`, `useCurrentLocation`, `geolocating`, `makeDefault`, `labelLabel`, `labelPlaceholder`, `saveAddressError`. The button label itself uses `Account.addresses.addAddress` ("Add address").

No new translation keys required if reuse is taken. If a cleaner separation is preferred later, the same strings can be duplicated under `Address.*` without API impact — pure i18n refactor.

## CSS changes

`AddressPicker.module.css`:

- New `.header` wrapper: `display: flex; align-items: center; justify-content: space-between; gap: var(--space-2)`. Wraps the existing `<label>` and the new add button.
- New `.addBtn` class for the outline button (small, secondary). Reuse global `btn btn-outline` if it composes cleanly; otherwise scope a module class.

## Validation + error handling

Mirror the addresses-page patterns exactly so the form behaves identically across surfaces:

- Field errors via `validationErrorsForPrefix(error, "address")` → `<AddressFields errors={...}>`.
- Top-of-modal error banner (or inline near footer) for non-validation errors, populated via `apiErrorKey` translation fallback.
- Disable Save button + AddressFields while `saving`.
- "Use current location" disabled while `saving || geolocating`.

## Risks + gotchas

- **`<AddressFields>` + map pin require `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY`.** Already provisioned (same as `/account/addresses`). No env-var changes.
- **Serviceability re-check is per-address.** When a new row is appended, the existing effect re-checks **all** addresses (not just the new one). Cost: ~1 extra `/api/v1/geo/serviceability` call per existing address. Acceptable — the picker is short-lived and the route is rate-limited per-IP (`GEO_RATE_LIMIT_PER_MIN=30`), and serviceability responses are Redis-cached.
- **`didAutoSelect.current` interaction.** The save handler explicitly bypasses the auto-select gate by calling `onChange(newId)` directly. Do not reset the ref to `false`, or the gate-reopen could later cause an unwanted re-select on an unrelated render.
- **POST returns full profile, not the new address.** Use the prev-ids diff approach above. If the diff returns no result (theoretically — backend would have to return an unchanged list), fall back to refetching profile without auto-selecting; the user can pick from the dropdown.
- **Modal close paths.** Backdrop click, Escape, header ✕, and Cancel button all close the modal and discard form state. No "are you sure?" prompt (consistent with existing modals).

## Out of scope follow-ups

- Server-side could be enhanced later to return just the new `CustomerAddress` from POST (cleaner than the diff). Not required now.
- The `/account/settings` → `/account/profile` redirect chain could be cleaned up (real route is `/account/addresses`), but that is outside this spec.

## Manual verification checklist

1. Logged-in customer with no saved addresses opens `/checkout/<storeId>/<serviceId>` → sees empty state with Add Address button (no stale `/account/settings` link).
2. Click Add Address → modal opens.
3. Geolocate → AddressFields populate, map pin shows current location.
4. Save → modal closes, dropdown shows the new address auto-selected. Place-order button transitions through "Checking delivery area" then enables (if address is in-radius) or stays disabled (if out-of-radius, with the suffix shown on the option).
5. Add a second address while one is already selected → new one becomes the selection (overrides prior).
6. Submit with invalid pincode → modal stays open, field error shown under the pincode input.
7. Cancel / Escape / backdrop click → modal closes, no address created, prior selection intact.
8. Repeat the flow on each of en, hi, mr, gu, pa to confirm all reused translation keys render.
