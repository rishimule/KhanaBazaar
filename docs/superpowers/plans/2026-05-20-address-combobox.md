# Address Combobox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the native `<select>` in `AddressPicker.tsx` with a custom ARIA combobox so outside-delivery-area addresses stay visible (in a separate, labelled section) but cannot be selected.

**Architecture:** All changes are scoped to `AddressPicker.tsx` + its CSS + 5 locale files. Custom combobox is a `<button>` + `<ul role="listbox">`, no external library. `aria-activedescendant` shifts virtual focus while DOM focus stays on the trigger. Document mousedown listener closes the listbox on outside clicks. Outside-area addresses render under a `role="presentation"` section header with `aria-disabled="true"` and a localized "Outside area" badge.

**Tech Stack:** React 19, TypeScript, Next.js 16 App Router, next-intl, CSS Modules.

**Reference spec:** `docs/superpowers/specs/2026-05-20-address-combobox-design.md`

**Branch:** `feat/checkout-add-address` (continue on this branch; current PR scope already covers the picker).

---

## Task 1: Add translation keys for outside-area header + badge

The hardcoded English `" (Outside delivery area)"` suffix is replaced by two translatable strings under the existing `Address` namespace.

**Files:**
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/hi.json`
- Modify: `frontend/messages/mr.json`
- Modify: `frontend/messages/gu.json`
- Modify: `frontend/messages/pa.json`

- [ ] **Step 1: Locate the `Address` namespace in en.json**

The block starts at `en.json:312`. Find the line containing `"noServiceableTitle": ...` followed by `"fallbackLabel": ...`. Add two new keys between them.

Replace this snippet in `frontend/messages/en.json`:

```jsonc
    "noServiceableTitle": "No saved address is within this store's delivery area.",
    "fallbackLabel": "Address",
```

With:

```jsonc
    "noServiceableTitle": "No saved address is within this store's delivery area.",
    "outsideDeliveryAreaHeader": "Outside delivery area",
    "outsideAreaBadge": "Outside area",
    "fallbackLabel": "Address",
```

- [ ] **Step 2: Add the same keys to hi.json (Hindi)**

Edit `frontend/messages/hi.json` in the same `Address` block. Use these Hindi translations:

```jsonc
    "noServiceableTitle": "इस स्टोर के डिलीवरी क्षेत्र में कोई सहेजा गया पता नहीं है।",
    "outsideDeliveryAreaHeader": "डिलीवरी क्षेत्र के बाहर",
    "outsideAreaBadge": "क्षेत्र के बाहर",
    "fallbackLabel": "पता",
```

- [ ] **Step 3: Add the same keys to mr.json (Marathi)**

Edit `frontend/messages/mr.json`:

```jsonc
    "noServiceableTitle": "या दुकानाच्या वितरण क्षेत्रात कोणताही जतन केलेला पत्ता नाही.",
    "outsideDeliveryAreaHeader": "वितरण क्षेत्राबाहेर",
    "outsideAreaBadge": "क्षेत्राबाहेर",
    "fallbackLabel": "पत्ता",
```

- [ ] **Step 4: Add the same keys to gu.json (Gujarati)**

Edit `frontend/messages/gu.json`:

```jsonc
    "noServiceableTitle": "આ સ્ટોરના ડિલિવરી વિસ્તારમાં કોઈ સાચવેલ સરનામું નથી.",
    "outsideDeliveryAreaHeader": "ડિલિવરી વિસ્તારની બહાર",
    "outsideAreaBadge": "વિસ્તારની બહાર",
    "fallbackLabel": "સરનામું",
```

- [ ] **Step 5: Add the same keys to pa.json (Punjabi)**

Edit `frontend/messages/pa.json`:

```jsonc
    "noServiceableTitle": "ਇਸ ਸਟੋਰ ਦੇ ਡਿਲੀਵਰੀ ਖੇਤਰ ਵਿੱਚ ਕੋਈ ਸੰਭਾਲਿਆ ਪਤਾ ਨਹੀਂ ਹੈ।",
    "outsideDeliveryAreaHeader": "ਡਿਲੀਵਰੀ ਖੇਤਰ ਤੋਂ ਬਾਹਰ",
    "outsideAreaBadge": "ਖੇਤਰ ਤੋਂ ਬਾਹਰ",
    "fallbackLabel": "ਪਤਾ",
```

- [ ] **Step 6: Validate JSON + run lint**

From the repo root:

```
cd frontend
for f in messages/en.json messages/hi.json messages/mr.json messages/gu.json messages/pa.json; do
  python3 -c "import json; json.load(open('$f'))" && echo "$f OK" || echo "$f INVALID"
done
npm run lint
```

Expected: all five `OK` lines. `npm run lint` should not introduce any new errors beyond the pre-existing 10 problems on `main`.

- [ ] **Step 7: Commit**

```
cd /home/rishi/Desktop/KhanaBazaar
git add frontend/messages/en.json frontend/messages/hi.json frontend/messages/mr.json frontend/messages/gu.json frontend/messages/pa.json
git commit -m "feat(i18n): add outside-delivery-area header + badge keys"
```

---

## Task 2: Add CSS for the combobox trigger, listbox, options, and section header

This task adds the styling required by the new combobox JSX. The trigger replaces the native `<select>` visually; the listbox is positioned absolutely below it.

**Files:**
- Modify: `frontend/src/components/orders/AddressPicker.module.css`

- [ ] **Step 1: Make `.picker` a positioning anchor**

The listbox is positioned absolutely against the picker root. Update `.picker` (the first rule in the file) to add `position: relative`:

```css
.picker {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-family: var(--font-family-sans);
}
```

- [ ] **Step 2: Append combobox styles to the end of the file**

Add the following block to the end of `frontend/src/components/orders/AddressPicker.module.css`:

```css
.comboTrigger {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 12px 14px;
  border-radius: var(--radius-card);
  border: 1px solid var(--shade-cool-light-6);
  font-family: var(--font-family-sans);
  font-size: var(--body-sm);
  background: var(--white);
  color: var(--shade-cool-dark-7);
  text-align: left;
  cursor: pointer;
  width: 100%;
  min-width: 0;
}

.comboTrigger:focus {
  outline: none;
  border-color: var(--color-primary-1);
  box-shadow: 0 0 0 2px rgba(184, 71, 15, 0.12);
}

.comboTrigger:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.comboLabel {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comboPlaceholder {
  color: var(--shade-cool-base-5);
}

.comboChevron {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  color: var(--shade-cool-base-5);
  transition: transform 120ms ease;
}

.comboTrigger[aria-expanded="true"] .comboChevron {
  transform: rotate(180deg);
}

.listbox {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  z-index: 50;
  margin: 0;
  padding: 4px 0;
  list-style: none;
  background: var(--white);
  border: 1px solid var(--shade-cool-light-6);
  border-radius: var(--radius-card);
  box-shadow: 0 8px 24px rgba(7, 16, 26, 0.12);
  max-height: 320px;
  overflow-y: auto;
}

.option {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 10px 14px;
  font-size: var(--body-sm);
  color: var(--shade-cool-dark-7);
  cursor: pointer;
  min-height: 44px;
}

.option[data-active="true"] {
  background: rgba(184, 71, 15, 0.08);
}

.optionSelected .optionCheck {
  color: var(--color-primary-1);
}

.optionLabel {
  flex: 0 0 auto;
  font-weight: var(--weight-semibold);
}

.optionAddress {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--shade-cool-base-5);
}

.optionCheck {
  flex: 0 0 auto;
  width: 16px;
  display: inline-flex;
  justify-content: center;
  color: transparent;
}

.option[aria-disabled="true"] {
  cursor: not-allowed;
  color: var(--shade-cool-base-5);
}

.option[aria-disabled="true"] .optionAddress {
  color: var(--shade-cool-base-4);
}

.optionBadge {
  flex: 0 0 auto;
  font-size: 11px;
  font-weight: var(--weight-semibold);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--shade-cool-light-5);
  color: var(--shade-cool-dark-3);
}

.sectionHeader {
  padding: 8px 14px 4px;
  font-size: 11px;
  font-weight: var(--weight-semibold);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--shade-cool-base-5);
  border-top: 1px solid var(--shade-cool-light-6);
  margin-top: 4px;
}

.sectionHeader:first-child {
  border-top: none;
  margin-top: 0;
}
```

- [ ] **Step 3: Verify required design tokens exist**

Run:

```
grep -E "(\-\-shade\-cool\-base\-4|\-\-shade\-cool\-base\-5|\-\-shade\-cool\-light\-5|\-\-shade\-cool\-dark\-3):" frontend/src/styles/design-tokens.css
```

Expected: at least 3 matches. If `--shade-cool-light-5` is absent, substitute `var(--shade-cool-light-6)` in the `.optionBadge` rule. If `--shade-cool-base-4` is absent, substitute `var(--shade-cool-base-5)` in the `.option[aria-disabled="true"] .optionAddress` rule. (Tokens may have been renamed; the grep tells you exactly what is available.)

- [ ] **Step 4: Lint**

```
cd frontend
npm run lint
```

Expected: same pre-existing 10 lint problems, no new ones.

- [ ] **Step 5: Commit**

```
cd /home/rishi/Desktop/KhanaBazaar
git add frontend/src/components/orders/AddressPicker.module.css
git commit -m "feat(checkout): CSS for custom address combobox + outside-area badge"
```

---

## Task 3: Replace the `<select>` JSX with a custom combobox

This is the largest task. It introduces the combobox state, refs, keyboard handlers, and JSX. The existing dropdown, both empty-state branches, the modal, and all of the picker's other behaviour stay intact.

**Files:**
- Modify: `frontend/src/components/orders/AddressPicker.tsx`

- [ ] **Step 1: Update imports**

Replace the existing `useEffect, useRef, useState` import at line 5 with:

```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
```

(Adds `useCallback` and `useMemo`.)

- [ ] **Step 2: Add combobox state + refs**

Below the existing `const [geolocating, setGeolocating] = useState(false);` line, add:

```tsx
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const listboxRef = useRef<HTMLUListElement | null>(null);
  const optionRefs = useRef<Map<number, HTMLLIElement>>(new Map());
```

The `optionRefs` map holds DOM refs keyed by address id so we can scroll the active row into view.

- [ ] **Step 3: Add the derived visible-options + section helpers**

Below the `const isDisabled = (id: number) => …` line near the bottom of the component (the picker already declares this near line 422 in the post-Task-2 baseline), add:

```tsx
  const { deliverableOptions, outsideOptions, visibleOptions } = useMemo(() => {
    const def = addresses.find((a) => a.is_default);

    // While serviceability is still loading (or storeId is undefined),
    // show every address as deliverable so the listbox is never empty.
    // The `allSettled` variable already declared earlier in the component
    // tells us whether serviceability is resolved.
    const deliverable = !allSettled || storeId === undefined
      ? [...addresses]
      : addresses.filter((a) => serviceability[a.id] === true);
    const outside = !allSettled || storeId === undefined
      ? []
      : addresses.filter((a) => serviceability[a.id] === false);

    // Default-flagged serviceable address sorts first within deliverable.
    const deliverableOrdered = def && deliverable.includes(def)
      ? [def, ...deliverable.filter((a) => a.id !== def.id)]
      : deliverable;

    const flat: { id: number; selectable: boolean }[] = [
      ...deliverableOrdered.map((a) => ({ id: a.id, selectable: true })),
      ...outside.map((a) => ({ id: a.id, selectable: false })),
    ];
    return {
      deliverableOptions: deliverableOrdered,
      outsideOptions: outside,
      visibleOptions: flat,
    };
  }, [addresses, serviceability, storeId, allSettled]);

  const selectedAddress = useMemo(
    () => addresses.find((a) => a.id === value) ?? null,
    [addresses, value],
  );

  const indexById = useCallback(
    (id: number | null) => {
      if (id == null) return -1;
      return visibleOptions.findIndex((o) => o.id === id);
    },
    [visibleOptions],
  );

  const firstSelectableIndex = useCallback(() => {
    return visibleOptions.findIndex((o) => o.selectable);
  }, [visibleOptions]);
```

- [ ] **Step 4: Add keyboard-navigation helpers**

Below the helpers from Step 3, add:

```tsx
  const moveActive = useCallback(
    (dir: 1 | -1) => {
      if (visibleOptions.length === 0) return;
      let i = activeIndex;
      for (let step = 0; step < visibleOptions.length; step += 1) {
        i = (i + dir + visibleOptions.length) % visibleOptions.length;
        if (visibleOptions[i].selectable) {
          setActiveIndex(i);
          return;
        }
      }
    },
    [activeIndex, visibleOptions],
  );

  const moveToFirst = useCallback(() => {
    const i = firstSelectableIndex();
    if (i >= 0) setActiveIndex(i);
  }, [firstSelectableIndex]);

  const moveToLast = useCallback(() => {
    for (let i = visibleOptions.length - 1; i >= 0; i -= 1) {
      if (visibleOptions[i].selectable) {
        setActiveIndex(i);
        return;
      }
    }
  }, [visibleOptions]);

  const closeListbox = useCallback(() => {
    setIsOpen(false);
    triggerRef.current?.focus();
  }, []);

  const selectActive = useCallback(() => {
    const opt = visibleOptions[activeIndex];
    if (!opt || !opt.selectable) return;
    onChange(opt.id);
    setIsOpen(false);
    triggerRef.current?.focus();
  }, [activeIndex, onChange, visibleOptions]);

  const openListbox = useCallback(() => {
    const current = indexById(value);
    const startAt =
      current >= 0 && visibleOptions[current]?.selectable
        ? current
        : firstSelectableIndex();
    if (startAt >= 0) setActiveIndex(startAt);
    setIsOpen(true);
  }, [indexById, value, visibleOptions, firstSelectableIndex]);
```

- [ ] **Step 5: Add the outside-click + Escape + modal-open effects**

Below the helpers, add three effects that wire up runtime behaviour:

```tsx
  // Close the listbox when the user opens the Add-Address modal.
  useEffect(() => {
    if (addModalOpen && isOpen) setIsOpen(false);
  }, [addModalOpen, isOpen]);

  // Document mousedown listener for outside-click close.
  useEffect(() => {
    if (!isOpen) return;
    const onMouseDown = (e: MouseEvent) => {
      const t = triggerRef.current;
      const lb = listboxRef.current;
      const target = e.target as Node | null;
      if (!target) return;
      if (t && t.contains(target)) return;
      if (lb && lb.contains(target)) return;
      setIsOpen(false);
    };
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [isOpen]);

  // Scroll the active option into view when the index changes (keyboard only;
  // mouse-driven changes are already in viewport).
  useEffect(() => {
    if (!isOpen) return;
    const opt = visibleOptions[activeIndex];
    if (!opt) return;
    const el = optionRefs.current.get(opt.id);
    el?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, isOpen, visibleOptions]);
```

- [ ] **Step 6: Add the keyboard handler**

Below the effects, add:

```tsx
  const onTriggerKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLButtonElement>) => {
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          if (!isOpen) {
            openListbox();
          } else {
            moveActive(1);
          }
          break;
        case "ArrowUp":
          e.preventDefault();
          if (!isOpen) {
            openListbox();
          } else {
            moveActive(-1);
          }
          break;
        case "Home":
          if (isOpen) {
            e.preventDefault();
            moveToFirst();
          }
          break;
        case "End":
          if (isOpen) {
            e.preventDefault();
            moveToLast();
          }
          break;
        case "Enter":
        case " ":
          if (isOpen) {
            e.preventDefault();
            selectActive();
          } else {
            e.preventDefault();
            openListbox();
          }
          break;
        case "Escape":
          if (isOpen) {
            e.preventDefault();
            closeListbox();
          }
          break;
        case "Tab":
          if (isOpen) setIsOpen(false);
          break;
        default:
          break;
      }
    },
    [
      isOpen,
      openListbox,
      moveActive,
      moveToFirst,
      moveToLast,
      selectActive,
      closeListbox,
    ],
  );
```

- [ ] **Step 7: Replace the main return's `<select>` JSX with the combobox**

Find the existing main return block (the one that renders the `<select id="address-picker">`). Replace it with the following. Note: `{addModalOpen && renderAddModal()}` is preserved at the end.

```tsx
  const activeOptionId =
    isOpen && visibleOptions[activeIndex]
      ? `addr-opt-${visibleOptions[activeIndex].id}`
      : undefined;

  const triggerLabel = selectedAddress
    ? `${selectedAddress.label ?? t("fallbackLabel")} — ${selectedAddress.address.address_line1}, ${selectedAddress.address.city} ${selectedAddress.address.pincode}`
    : t("fallbackLabel");

  return (
    <>
      <div className={styles.picker}>
        <div className={styles.header}>
          <span id="addr-picker-label" className={styles.label}>
            {t("deliverTo")}
          </span>
          <button
            type="button"
            className={styles.addBtn}
            onClick={openAddModal}
          >
            + {tAcc("addAddress")}
          </button>
        </div>
        <button
          ref={triggerRef}
          type="button"
          className={styles.comboTrigger}
          role="combobox"
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          aria-controls="addr-listbox"
          aria-labelledby="addr-picker-label"
          aria-activedescendant={activeOptionId}
          onClick={() => (isOpen ? setIsOpen(false) : openListbox())}
          onKeyDown={onTriggerKeyDown}
          onBlur={(e) => {
            const next = e.relatedTarget as Node | null;
            const lb = listboxRef.current;
            if (next && lb && lb.contains(next)) return;
            if (isOpen) setIsOpen(false);
          }}
        >
          <span
            className={`${styles.comboLabel} ${selectedAddress ? "" : styles.comboPlaceholder}`}
          >
            {triggerLabel}
          </span>
          <span className={styles.comboChevron} aria-hidden="true">▾</span>
        </button>
        {isOpen && (
          <ul
            ref={listboxRef}
            id="addr-listbox"
            role="listbox"
            tabIndex={-1}
            className={styles.listbox}
          >
            {deliverableOptions.map((a) => {
              const idx = visibleOptions.findIndex((o) => o.id === a.id);
              const selected = a.id === value;
              const isActive = idx === activeIndex;
              return (
                <li
                  key={a.id}
                  ref={(el) => {
                    if (el) optionRefs.current.set(a.id, el);
                    else optionRefs.current.delete(a.id);
                  }}
                  id={`addr-opt-${a.id}`}
                  role="option"
                  aria-selected={selected}
                  data-active={isActive ? "true" : undefined}
                  className={`${styles.option} ${selected ? styles.optionSelected : ""}`}
                  onMouseEnter={() => setActiveIndex(idx)}
                  onClick={() => {
                    onChange(a.id);
                    setIsOpen(false);
                    triggerRef.current?.focus();
                  }}
                >
                  <span className={styles.optionCheck} aria-hidden="true">
                    {selected ? "✓" : ""}
                  </span>
                  <span className={styles.optionLabel}>
                    {a.label ?? t("fallbackLabel")}
                  </span>
                  <span className={styles.optionAddress}>
                    {a.address.address_line1}, {a.address.city} {a.address.pincode}
                  </span>
                </li>
              );
            })}
            {outsideOptions.length > 0 && (
              <li
                role="presentation"
                className={styles.sectionHeader}
                aria-hidden="true"
              >
                {t("outsideDeliveryAreaHeader")}
              </li>
            )}
            {outsideOptions.map((a) => {
              const idx = visibleOptions.findIndex((o) => o.id === a.id);
              const isActive = idx === activeIndex;
              return (
                <li
                  key={a.id}
                  ref={(el) => {
                    if (el) optionRefs.current.set(a.id, el);
                    else optionRefs.current.delete(a.id);
                  }}
                  id={`addr-opt-${a.id}`}
                  role="option"
                  aria-selected={false}
                  aria-disabled="true"
                  data-active={isActive ? "true" : undefined}
                  className={styles.option}
                >
                  <span className={styles.optionCheck} aria-hidden="true" />
                  <span className={styles.optionLabel}>
                    {a.label ?? t("fallbackLabel")}
                  </span>
                  <span className={styles.optionAddress}>
                    {a.address.address_line1}, {a.address.city} {a.address.pincode}
                  </span>
                  <span className={styles.optionBadge}>
                    {t("outsideAreaBadge")}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      {addModalOpen && renderAddModal()}
    </>
  );
}
```

- [ ] **Step 8: Remove the now-unused `isDisabled` helper**

Find the line:

```tsx
  const isDisabled = (id: number) =>
    storeId !== undefined && serviceability[id] === false;
```

Delete it. The new JSX no longer uses it. Leaving it triggers an unused-variable lint warning.

- [ ] **Step 9: Remove the dead `(Outside delivery area)` literal**

If your grep finds any residual `"(Outside delivery area)"` string literal in `AddressPicker.tsx` (it should have been carried in the old `<select><option>` block), confirm it is gone after the Step 7 replacement. The combobox renders the badge via `t("outsideAreaBadge")` and never inlines the English literal.

```
grep -n "Outside delivery area" frontend/src/components/orders/AddressPicker.tsx
```

Expected: no matches.

- [ ] **Step 10: Lint + build**

From `frontend/`:

```
npm run lint
npm run build
```

Expected:
- `npm run lint`: same pre-existing 10 problems, no new errors.
- `npm run build`: completes with route listing, no TypeScript errors.

If you see "X is defined but never used" for `isDisabled`, confirm Step 8 was applied. If TypeScript complains about a missing `t("outsideDeliveryAreaHeader")` or `t("outsideAreaBadge")` translation key (next-intl strict checking), confirm Task 1 added those keys to all five locale files.

- [ ] **Step 11: Commit**

```
cd /home/rishi/Desktop/KhanaBazaar
git add frontend/src/components/orders/AddressPicker.tsx
git commit -m "feat(checkout): custom ARIA combobox with outside-area section"
```

---

## Task 4: Manual verification on dev stack

No frontend tests exist; verification is manual.

**Files:** None modified in this task.

- [ ] **Step 1: Start dev stack**

```
./scripts/dev.sh start
```

Expected: postgres, redis, meilisearch, backend, celery, frontend all running.

- [ ] **Step 2: Set up the test customer**

Log in as a customer with at least four saved addresses:

- 2 inside the test store's delivery radius (one marked default)
- 2 outside the radius (e.g., set far-away coordinates via the geolocate flow on `/account/addresses`)

If you do not already have such a profile, add the addresses via `/account/addresses` before continuing.

- [ ] **Step 3: Reach a checkout page**

Add a product to the cart, go to `/cart`, click `Checkout` for the relevant service. Land on `/checkout/<storeId>/<serviceId>`.

- [ ] **Step 4: Walk the verification checklist**

For each item, confirm the behaviour matches; record any failure.

1. The "Deliver to" header row + "+ Add address" button render unchanged.
2. The trigger button renders the currently-selected (in-radius) address on a single line, ellipsised, with a chevron on the right.
3. Click the trigger → listbox opens beneath it.
4. The two in-radius addresses appear first, default-flagged one at the top, with a `✓` to the left of the selected one.
5. Below them, a small uppercase "Outside delivery area" header (or its localized form) appears.
6. Below the header, the two out-of-radius addresses appear, greyed, with an "Outside area" pill at the right of each row.
7. Click an outside-area row → nothing happens; cursor shows `not-allowed`; listbox stays open.
8. Click an in-radius row → the row is selected; listbox closes; trigger updates to the new selection.
9. Open the listbox, press ArrowDown repeatedly → focus ring moves only across the two in-radius rows, wrapping back to the first after the second.
10. Press ArrowUp from the top in-radius row → focus ring jumps to the last in-radius row (wrap behaviour).
11. Press Home → first in-radius row gets focus ring. Press End → last in-radius row gets focus ring.
12. Press Enter on a focused in-radius row → selects; listbox closes; trigger retains focus.
13. Press Escape → listbox closes; trigger retains focus.
14. Click outside the picker → listbox closes.
15. Press Tab while open → listbox closes; focus moves on naturally.
16. Click "+ Add address" while listbox is open → listbox closes; modal opens.
17. Repeat steps 3–8 in each locale (`/en/`, `/hi/`, `/mr/`, `/gu/`, `/pa/`) and confirm the section header + badge text use the localized strings.
18. Place an order using a serviceable address. Confirm the place-order flow still works end-to-end.

- [ ] **Step 5: Browser dev-tools accessibility check**

Open Chrome DevTools → "Accessibility" pane. Inspect the trigger button:
- `role` is `combobox`
- `aria-haspopup` is `listbox`
- `aria-expanded` toggles between `true` and `false` as you open / close
- `aria-controls` is `addr-listbox`
- `aria-activedescendant` is `addr-opt-{id}` for the currently-active option when open

Inspect a few `<li>` rows:
- In-radius rows have `role="option"`, `aria-selected="true"` for the selected one.
- Out-of-radius rows have `role="option"`, `aria-disabled="true"`.
- The section header `<li>` has `role="presentation"`.

- [ ] **Step 6: Mobile viewport check**

Toggle Chrome devtools mobile viewport (375 × 667). Confirm:
- Trigger fits on one line with ellipsis.
- Listbox does not overflow the viewport horizontally.
- Tapping a row works the same as clicking.
- The chevron rotates 180° while the listbox is open.

- [ ] **Step 7: Stop dev stack**

```
./scripts/dev.sh stop
```

- [ ] **Step 8: Push branch**

```
git push -u origin feat/checkout-add-address
```

Do **not** open the PR. The user opens PRs manually per `CLAUDE.md`.

---

## Notes for executor

- **Branch** `feat/checkout-add-address` already contains the prior Add-Address-modal work + the spec for this combobox change. Stay on this branch.
- **No backend changes.** Serviceability data is already produced by the existing `/api/v1/geo/serviceability` flow.
- **No new dependencies.** Combobox is raw React.
- **`useTranslations("Address")`** is the existing namespace (variable `t`). The new keys live there, so no second `useTranslations` call is required for this feature.
- **Pre-existing 10 lint problems** on `main` are unrelated and remain. Confirm no *new* lint issues; do not fix the pre-existing ones in this task.
- **Conventional Commits, no AI co-author trailers, no `--no-verify`, no `--amend`** per `CLAUDE.md`.
- **Final state at end of Task 3** — the old `<select>` JSX is fully gone; the `<label htmlFor="address-picker">` is now a `<span id="addr-picker-label">` referenced via `aria-labelledby`.

## Spec coverage map

| Spec section | Task / Step |
|---|---|
| Trigger button + ARIA attrs | Task 3 Step 7 |
| Listbox popover + role attributes | Task 3 Step 7 |
| Row layout incl. selected check, label, address, badge | Task 3 Step 7 |
| Section header `role="presentation"` | Task 3 Step 7 |
| Sorting (default first, then deliverable, then outside-area) | Task 3 Step 3 |
| State + refs | Task 3 Steps 2–4 |
| Open / close behaviour | Task 3 Steps 4, 6, 7 |
| Keyboard nav (Arrow / Home / End / Enter / Space / Escape / Tab) | Task 3 Step 6 |
| Mouse / touch interactions | Task 3 Step 7 |
| Scroll active option into view | Task 3 Step 5 |
| Outside-click close + Escape | Task 3 Step 5, Step 6 |
| Close listbox when modal opens | Task 3 Step 5 |
| Translation keys | Task 1 |
| CSS for trigger / listbox / option / badge / header | Task 2 |
| Edge cases (loading, all-outside, no addresses, storeId undefined) | Task 3 Step 3 + existing branches preserved |
| Accessibility checklist | Task 4 Step 5 |
| Mobile UX | Task 4 Step 6 |
| Manual verification checklist | Task 4 Step 4 |
