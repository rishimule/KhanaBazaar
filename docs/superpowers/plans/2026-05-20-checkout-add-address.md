# Checkout — Add Address Inline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a customer add a new delivery address from inside the checkout page via a modal, without leaving the flow. The newly added address auto-selects in the picker.

**Architecture:** All changes are scoped to the existing `<AddressPicker>` component used on the checkout page. The modal lives inside `AddressPicker`, owns its own form state, posts to `POST /api/v1/customers/me/addresses`, and refreshes the picker's address list from the server response. The picker's existing serviceability-check effect handles re-validating the new address against the store's delivery radius automatically. No backend changes. No new components.

**Tech Stack:** Next.js 16 (App Router), React 19, TypeScript, CSS Modules, next-intl, existing `<Modal>` + `<AddressFields>` + `/api/v1/geo/reverse` + `/api/v1/customers/me/addresses`.

**Reference spec:** `docs/superpowers/specs/2026-05-20-checkout-add-address-design.md`

**Branch:** `feat/checkout-add-address` (already created and contains the spec commit).

---

## Task 1: CSS — header row + Add Address button styles

**Files:**
- Modify: `frontend/src/components/orders/AddressPicker.module.css`

- [ ] **Step 1: Add header row + addBtn styles**

Append the following blocks to `frontend/src/components/orders/AddressPicker.module.css` (after the existing `.link:hover` rule on line 45):

```css
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.addBtn {
  font-family: var(--font-family-sans);
  font-size: var(--body-sm);
  font-weight: var(--weight-semibold);
  color: var(--color-primary-1);
  background: transparent;
  border: 1px solid var(--color-primary-1);
  border-radius: var(--radius-card);
  padding: 6px 12px;
  cursor: pointer;
  white-space: nowrap;
}

.addBtn:hover:not(:disabled) {
  background: rgba(184, 71, 15, 0.06);
}

.addBtn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.emptyActions {
  margin-top: var(--space-2);
}

.modalBody {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.modalField {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.modalInput {
  padding: 10px 12px;
  border-radius: var(--radius-card);
  border: 1px solid var(--shade-cool-light-6);
  font-family: var(--font-family-sans);
  font-size: var(--body-sm);
  background: var(--white);
  color: var(--shade-cool-dark-7);
}

.modalInput:focus {
  outline: none;
  border-color: var(--color-primary-1);
  box-shadow: 0 0 0 2px rgba(184, 71, 15, 0.12);
}

.modalCheckboxRow {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--body-sm);
  color: var(--shade-cool-dark-7);
}

.modalActions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  margin-top: var(--space-2);
}

.modalError {
  background: rgba(220, 38, 38, 0.08);
  color: rgb(153, 27, 27);
  padding: 8px 12px;
  border-radius: var(--radius-card);
  font-size: var(--body-sm);
}
```

- [ ] **Step 2: Verify lint (no JS impact, but make sure CSS Modules picks up the new classes)**

Run from `frontend/`:

```
npm run lint
```

Expected: no errors (no JS changed, lint should pass).

- [ ] **Step 3: Commit**

```
git add frontend/src/components/orders/AddressPicker.module.css
git commit -m "feat(checkout): add CSS for inline Add Address modal styles"
```

---

## Task 2: AddressPicker — implement Add Address modal

This task wires up the full feature in one commit so intermediate states compile cleanly. Each step below is bite-sized.

**Files:**
- Modify: `frontend/src/components/orders/AddressPicker.tsx`

- [ ] **Step 1: Update imports**

Replace the import block at the top of `frontend/src/components/orders/AddressPicker.tsx` (lines 5-11) with:

```tsx
import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { checkServiceability } from "@/lib/geo";
import { apiErrorKey } from "@/lib/errors";
import Modal from "@/components/Modal";
import {
  AddressFields,
  emptyAddress,
  type AddressFieldsErrors,
} from "@/components/AddressFields";
import type { Address, CustomerProfile } from "@/types";
import styles from "./AddressPicker.module.css";
```

Notes:
- Drop the `Link` import — both stale `/account/settings` links are getting removed.
- Add `post` from `@/lib/api`.
- Add `apiErrorKey` from `@/lib/errors`.
- Add `Modal`, `AddressFields`, `emptyAddress`, `AddressFieldsErrors` from existing modules.
- Add `Address`, `CustomerProfile` type imports.

- [ ] **Step 2: Add new state inside the component**

In the component body (immediately after the existing `didAutoSelect` ref, currently line 65), add the modal/form state:

```tsx
  const tAcc = useTranslations("Account.addresses");
  const tErr = useTranslations("Errors");

  const [addModalOpen, setAddModalOpen] = useState(false);
  const [addForm, setAddForm] = useState<{
    label: string;
    is_default: boolean;
    address: Address;
  }>({ label: "", is_default: false, address: emptyAddress() });
  const [addErrors, setAddErrors] = useState<AddressFieldsErrors>({});
  const [modalError, setModalError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [geolocating, setGeolocating] = useState(false);
```

- [ ] **Step 3: Add the openAddModal handler**

Immediately after the new state, add:

```tsx
  const openAddModal = () => {
    setAddForm({ label: "", is_default: false, address: emptyAddress() });
    setAddErrors({});
    setModalError(null);
    setAddModalOpen(true);
  };

  const closeAddModal = () => {
    if (saving) return;
    setAddModalOpen(false);
  };
```

- [ ] **Step 4: Add the useCurrentLocation handler**

After `closeAddModal`, add:

```tsx
  const useCurrentLocation = () => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setModalError(tAcc("geolocationUnavailable"));
      return;
    }
    setModalError(null);
    setGeolocating(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude, longitude } = pos.coords;
        try {
          const place = await get<{
            address_line1?: string;
            city?: string;
            state?: string;
            pincode?: string;
            country?: string;
            latitude: number;
            longitude: number;
          }>(`/api/v1/geo/reverse?lat=${latitude}&lng=${longitude}`, token);
          setAddForm((curr) => ({
            ...curr,
            address: {
              ...curr.address,
              address_line1: place.address_line1 ?? curr.address.address_line1,
              city: place.city ?? curr.address.city,
              state: place.state ?? curr.address.state,
              pincode: place.pincode ?? curr.address.pincode,
              country: place.country ?? curr.address.country,
              latitude,
              longitude,
              location_source: "geocoded",
            },
          }));
        } catch {
          setModalError(tAcc("geolocationGeocodeError"));
          setAddForm((curr) => ({
            ...curr,
            address: {
              ...curr.address,
              latitude,
              longitude,
              location_source: "geocoded",
            },
          }));
        } finally {
          setGeolocating(false);
        }
      },
      (err) => {
        setGeolocating(false);
        setModalError(
          err.code === err.PERMISSION_DENIED
            ? tAcc("geolocationDenied")
            : tAcc("geolocationError"),
        );
      },
    );
  };
```

- [ ] **Step 5: Add validation-error helper + save handler**

After `useCurrentLocation`, add:

```tsx
  const validationErrorsForPrefix = (
    error: unknown,
    prefix: string,
  ): Record<string, string> => {
    const detail = (error as { detail?: unknown })?.detail;
    if (!Array.isArray(detail)) return {};
    return detail.reduce<Record<string, string>>((acc, issue) => {
      const loc = (issue as { loc?: Array<string | number> }).loc;
      const msg = (issue as { msg?: string }).msg;
      if (!Array.isArray(loc) || typeof msg !== "string") return acc;
      const i = loc.indexOf(prefix);
      if (i === -1) return acc;
      const field = loc[i + 1];
      if (typeof field === "string") acc[field] = msg;
      return acc;
    }, {});
  };

  const onSaveAddress = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token || saving) return;
    setSaving(true);
    setAddErrors({});
    setModalError(null);
    const prevIds = new Set(addresses.map((a) => a.id));
    const payload = {
      label: addForm.label.trim().length > 0 ? addForm.label.trim() : null,
      is_default: addForm.is_default,
      address: addForm.address,
    };
    try {
      const next = await post<CustomerProfile>(
        "/api/v1/customers/me/addresses",
        payload,
        token,
      );
      const newId = next.addresses.find((a) => !prevIds.has(a.id))?.id ?? null;
      setAddresses(
        next.addresses.map((a) => ({
          id: a.id,
          label: a.label,
          is_default: a.is_default,
          address: {
            address_line1: a.address.address_line1,
            address_line2: a.address.address_line2 ?? null,
            city: a.address.city,
            state: a.address.state,
            pincode: a.address.pincode,
            latitude: a.address.latitude ?? null,
            longitude: a.address.longitude ?? null,
          },
        })),
      );
      setAddModalOpen(false);
      if (newId != null) {
        onChange(newId);
      }
    } catch (error) {
      setAddErrors(
        validationErrorsForPrefix(error, "address") as AddressFieldsErrors,
      );
      const key = apiErrorKey(error);
      if (key) {
        setModalError(tErr(key.replace(/^Errors\./, "")));
      } else {
        setModalError(tAcc("saveAddressError"));
      }
    } finally {
      setSaving(false);
    }
  };
```

Note on `setAddresses` mapping: the picker's local `CustomerAddressApi` type only carries a subset of `Address` fields. The mapping above projects the full `Address` returned by the server back into that shape so the rest of the picker keeps working. If the local interface ever widens to match the full `Address` type, this mapping can become `setAddresses(next.addresses)`.

- [ ] **Step 6: Wrap the existing label in the header row + add the button**

Find the existing dropdown JSX (currently lines 166-183):

```tsx
  return (
    <div className={styles.picker}>
      <label htmlFor="address-picker" className={styles.label}>{t("deliverTo")}</label>
      <select
        id="address-picker"
        value={value ?? ""}
        onChange={(e) => onChange(Number(e.target.value))}
        className={styles.select}
      >
        {addresses.map((a) => (
          <option key={a.id} value={a.id} disabled={isDisabled(a.id)}>
            {(a.label ?? t("fallbackLabel"))} — {a.address.address_line1}, {a.address.city} {a.address.pincode}
            {isDisabled(a.id) ? " (Outside delivery area)" : ""}
          </option>
        ))}
      </select>
    </div>
  );
```

Replace with:

```tsx
  return (
    <>
      <div className={styles.picker}>
        <div className={styles.header}>
          <label htmlFor="address-picker" className={styles.label}>{t("deliverTo")}</label>
          <button
            type="button"
            className={styles.addBtn}
            onClick={openAddModal}
          >
            + {tAcc("addAddress")}
          </button>
        </div>
        <select
          id="address-picker"
          value={value ?? ""}
          onChange={(e) => onChange(Number(e.target.value))}
          className={styles.select}
        >
          {addresses.map((a) => (
            <option key={a.id} value={a.id} disabled={isDisabled(a.id)}>
              {(a.label ?? t("fallbackLabel"))} — {a.address.address_line1}, {a.address.city} {a.address.pincode}
              {isDisabled(a.id) ? " (Outside delivery area)" : ""}
            </option>
          ))}
        </select>
      </div>
      {addModalOpen && renderAddModal()}
    </>
  );
```

(The `renderAddModal()` helper is defined in Step 8 below.)

- [ ] **Step 7: Replace both empty-state stale-link blocks**

Find the existing empty-state for "no addresses" (currently lines 141-148):

```tsx
  if (addresses.length === 0) {
    return (
      <div className={styles.empty}>
        {t("pickerEmpty")}{" "}
        <Link href="/account/settings" className={styles.link}>{t("pickerAddOne")}</Link>
      </div>
    );
  }
```

Replace with:

```tsx
  if (addresses.length === 0) {
    return (
      <>
        <div className={styles.empty}>
          {t("pickerEmpty")}
          <div className={styles.emptyActions}>
            <button
              type="button"
              className={styles.addBtn}
              onClick={openAddModal}
            >
              + {tAcc("addAddress")}
            </button>
          </div>
        </div>
        {addModalOpen && renderAddModal()}
      </>
    );
  }
```

Find the existing empty-state for "no serviceable" (currently lines 154-161):

```tsx
  if (allSettled && !hasAnyServiceable) {
    return (
      <div className={styles.empty}>
        {t("noServiceableTitle")}{" "}
        <Link href="/account/settings" className={styles.link}>{t("pickerAddOne")}</Link>
      </div>
    );
  }
```

Replace with:

```tsx
  if (allSettled && !hasAnyServiceable) {
    return (
      <>
        <div className={styles.empty}>
          {t("noServiceableTitle")}
          <div className={styles.emptyActions}>
            <button
              type="button"
              className={styles.addBtn}
              onClick={openAddModal}
            >
              + {tAcc("addAddress")}
            </button>
          </div>
        </div>
        {addModalOpen && renderAddModal()}
      </>
    );
  }
```

- [ ] **Step 8: Define `renderAddModal()` above the `return`**

Immediately before the `if (profileLoading) return ...` block (currently line 140), define the modal renderer:

```tsx
  const renderAddModal = () => (
    <Modal title={tAcc("addAddressFormTitle")} onClose={closeAddModal} size="wide">
      <form className={styles.modalBody} onSubmit={onSaveAddress}>
        {modalError && <div className={styles.modalError}>{modalError}</div>}

        <div className={styles.modalField}>
          <label className={styles.label} htmlFor="add-address-label">
            {tAcc("labelLabel")}
          </label>
          <input
            id="add-address-label"
            className={styles.modalInput}
            value={addForm.label}
            onChange={(e) =>
              setAddForm((curr) => ({ ...curr, label: e.target.value }))
            }
            placeholder={tAcc("labelPlaceholder")}
            maxLength={60}
            disabled={saving}
          />
        </div>

        <button
          type="button"
          className={styles.addBtn}
          onClick={useCurrentLocation}
          disabled={saving || geolocating}
        >
          {geolocating ? tAcc("geolocating") : tAcc("useCurrentLocation")}
        </button>

        <AddressFields
          value={addForm.address}
          onChange={(address) =>
            setAddForm((curr) => ({ ...curr, address }))
          }
          errors={addErrors}
          disabled={saving}
        />

        <label className={styles.modalCheckboxRow}>
          <input
            type="checkbox"
            checked={addForm.is_default}
            onChange={(e) =>
              setAddForm((curr) => ({ ...curr, is_default: e.target.checked }))
            }
            disabled={saving}
          />
          {tAcc("makeDefault")}
        </label>

        <div className={styles.modalActions}>
          <button
            type="button"
            className="btn btn-outline"
            onClick={closeAddModal}
            disabled={saving}
          >
            {tAcc("cancel")}
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={saving}
          >
            {saving ? tAcc("saving") : tAcc("saveAddress")}
          </button>
        </div>
      </form>
    </Modal>
  );
```

- [ ] **Step 9: Run lint**

From `frontend/`:

```
npm run lint
```

Expected: no errors, no new warnings.

If you see "X is defined but never used" for an old import (e.g. `Link`), it means a removal step was missed — go back to Step 1 and confirm the import block matches exactly.

- [ ] **Step 10: Run a typecheck via build**

From `frontend/`:

```
npm run build
```

Expected: build completes successfully (Next.js build runs `tsc`).

If TypeScript errors appear:
- Re-check the `setAddresses(...)` mapping in Step 5 — the `CustomerAddressApi` shape must match.
- Re-check `AddressFieldsErrors` is imported as a type-only import.
- Re-check the return type of `post<CustomerProfile>` and that `CustomerProfile.addresses` exists on the type. If not, inspect `frontend/src/types/index.ts` and adjust the response type (e.g. use a local response shape if `CustomerProfile` is not exported).

- [ ] **Step 11: Commit**

```
git add frontend/src/components/orders/AddressPicker.tsx
git commit -m "feat(checkout): inline Add Address modal in AddressPicker"
```

---

## Task 3: Verify locale parity for reused translation keys

The modal reuses keys from the `Account.addresses.*` namespace. They are confirmed present in `messages/en.json`. The other 4 locale files (`hi.json`, `mr.json`, `gu.json`, `pa.json`) must contain the same keys or `next-intl` will throw at render time.

**Files:**
- Read (and possibly modify): `frontend/messages/hi.json`, `frontend/messages/mr.json`, `frontend/messages/gu.json`, `frontend/messages/pa.json`

- [ ] **Step 1: Check each locale for the required keys**

Required keys under `Account.addresses` (all referenced by the new code):

- `addAddress`
- `addAddressFormTitle`
- `cancel`
- `saveAddress`
- `saving`
- `useCurrentLocation`
- `geolocating`
- `geolocationUnavailable`
- `geolocationDenied`
- `geolocationError`
- `geolocationGeocodeError`
- `makeDefault`
- `labelLabel`
- `labelPlaceholder`
- `saveAddressError`

For each of `hi.json`, `mr.json`, `gu.json`, `pa.json`, run:

```
grep -E '"(addAddress|addAddressFormTitle|cancel|saveAddress|saving|useCurrentLocation|geolocating|geolocationUnavailable|geolocationDenied|geolocationError|geolocationGeocodeError|makeDefault|labelLabel|labelPlaceholder|saveAddressError)":' frontend/messages/<locale>.json
```

Expected: 15 matches per file. If any key is missing, copy the English string from `en.json` as a placeholder (untranslated) — better to ship a stub than to crash the locale.

- [ ] **Step 2: Add any missing keys (only if Step 1 found gaps)**

For each missing key in a locale file, locate the `"addresses": { ... }` block (mirrors line 566 in `en.json`) and add the missing key with the English string as the value. Use the Edit tool. Example pattern (for `hi.json`):

```jsonc
// Before:
"saveAddress": "...existing hindi string or absent...",

// After (only if absent):
"saveAddress": "Save address",
```

(The English placeholder is acceptable per project precedent — translation refinement is a separate concern.)

- [ ] **Step 3: Lint to confirm JSON validity**

```
npm run lint
```

Expected: no errors.

- [ ] **Step 4: Commit (if any locale files changed)**

```
git add frontend/messages/
git commit -m "feat(checkout): ensure all locales have Account.addresses modal keys"
```

If no locale file was changed in Step 2, skip the commit and proceed.

---

## Task 4: Manual verification on dev stack

The project has no frontend tests (per `CLAUDE.md`); verification is manual.

**Files:** None modified in this task.

- [ ] **Step 1: Start dev stack**

```
./scripts/dev.sh start
```

Expected: postgres, redis, meilisearch, backend, celery, frontend all running.

- [ ] **Step 2: Seed data (if needed)**

If this is a fresh DB, run from `backend/app/`:

```
uv run python -m app.db.seed
```

This populates services, categories, products, and a sample seller/store. Skip if your local DB already has data.

- [ ] **Step 3: Walk through the verification checklist**

Open `http://localhost:3000` and:

1. Log in as a customer (use the email-OTP flow; OTP appears in the backend console logs).
2. If the customer has no saved addresses, add one via `/account/addresses` first OR skip and verify the empty-state path on checkout.
3. Browse to a store, add at least one product to the cart for a single service, go to cart, click "Checkout" for that service.
4. On the checkout page, locate the "Deliver to" section. Confirm:
   - The "+ Add address" outline button appears to the right of the "Deliver to" label.
   - The dropdown shows existing saved addresses.
5. Click the "+ Add address" button. Confirm:
   - A modal opens titled "Add delivery address".
   - The modal contains: optional label input, "Use current location" button, AddressFields (line1 / line2 / city / state / pincode + map pin), "Make this the default delivery address" checkbox, Cancel + Save Address buttons.
6. Click "Use current location". Grant geolocation in the browser. Confirm:
   - The address fields populate with reverse-geocoded values.
   - The map pin reflects the geocoded location.
7. Tweak any field (e.g. line1) and click Save Address. Confirm:
   - The modal closes.
   - The dropdown now shows the newly added address.
   - The new address is auto-selected (it's the active option).
   - The place-order button briefly shows "Checking delivery area" then either enables (in-radius) or stays disabled with the new address marked "(Outside delivery area)" if it's outside the store's radius.
8. Click "+ Add address" again. Submit with an invalid pincode (e.g., "12"). Confirm:
   - The modal stays open with an inline field error under the pincode input.
   - The localized error appears (English: "Could not save delivery address." or similar).
9. Close the modal via the header ✕ button, Cancel, Escape key, and backdrop click. Confirm each closes the modal and discards form state with the prior dropdown selection intact.
10. Switch the URL locale segment from `/en/` to `/hi/`. Repeat steps 5-7. Confirm the modal renders without errors and uses Hindi strings (or the English fallbacks added in Task 3).

- [ ] **Step 4: Confirm no console errors**

In the browser devtools console, confirm no red errors during the flow above. Yellow warnings from third-party libs (Google Maps) are acceptable.

- [ ] **Step 5: Stop the dev stack**

```
./scripts/dev.sh stop
```

- [ ] **Step 6: Push the branch (do not open PR — user opens PR manually)**

```
git push -u origin feat/checkout-add-address
```

Per project policy in `CLAUDE.md`: do **not** open the PR until the user explicitly approves.

---

## Notes for executor

- **Branch already exists:** `feat/checkout-add-address` was created when the spec was committed. Stay on this branch for all tasks.
- **No backend changes.** `POST /api/v1/customers/me/addresses` already exists and returns the full updated `CustomerProfile`.
- **TypeScript strictness:** if the local `CustomerAddressApi` interface in `AddressPicker.tsx` and the server's `CustomerAddress` shape diverge, the explicit mapping in Task 2 Step 5 keeps the picker's interface honest. Don't widen `CustomerAddressApi` to import the global `Address` type unless lint forces it — keep the change scoped.
- **No frontend tests required.** Verification is manual per Task 4.
- **Conventional Commits:** type `feat(checkout): ...` for code changes, type `docs(checkout): ...` was used for the spec, type `feat(checkout): ...` for translations or `chore(i18n): ...` are both acceptable.
- **No `--no-verify`, no `--amend`, no AI co-author trailers** (per CLAUDE.md).
