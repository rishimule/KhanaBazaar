# Checkout Address Picker — Custom Combobox with Outside-Area Section

**Date:** 2026-05-20
**Scope:** Frontend only (no backend changes)
**Touches:** `frontend/src/components/orders/AddressPicker.tsx`, `frontend/src/components/orders/AddressPicker.module.css`, `frontend/messages/*.json`

## Problem

Today the checkout-page `<AddressPicker>` uses a native HTML `<select>` and disables `<option>` elements whose addresses fall outside the store's delivery radius. The hardcoded English suffix `" (Outside delivery area)"` is appended to disabled option text.

Drawbacks of the native approach:
- Mobile native pickers (iOS / Android) render disabled options inconsistently — sometimes they are hidden, sometimes only slightly greyed.
- Disabled options have no distinct visual treatment, no badge, no section.
- The "Outside delivery area" suffix is English-only and was flagged in code review (Reviewer 3) as a localisation gap.
- The user cannot tell at a glance whether their target address is excluded from the list versus simply missing.

## Goal

Replace the native `<select>` inside `AddressPicker.tsx` with a custom ARIA combobox so that outside-area addresses remain visible but are not selectable. Group deliverable addresses at the top of the listbox; render a labelled "Outside delivery area" section beneath, containing the disabled rows.

## Non-goals

- Distance calculations or "X km away" labels.
- "Browse stores nearby" CTA on outside-area rows.
- Pulling in a headless-UI library (Radix, Headless UI, etc). The picker has one location of use; a raw React combobox is sufficient and avoids a runtime dependency.
- The `<select>` element inside `AddressFields.tsx` (state dropdown). Different surface, not in scope.
- Backend changes — serviceability data already comes from the existing `/api/v1/geo/serviceability` flow used by the picker today.

## UI specification

### Trigger button

Replaces the existing `<select>` element. Single-line button rendered immediately below the `Deliver to` / `+ Add address` header row.

```
[ Home — 123 Main St, Mumbai 400001                              ▾ ]
```

- Content: `{label or fallback} — {address_line1}, {city} {pincode}`. Truncated with `text-overflow: ellipsis`.
- Chevron glyph on the right (`▾` or SVG, design-token color).
- Attributes:
  - `type="button"`
  - `role="combobox"`
  - `aria-haspopup="listbox"`
  - `aria-expanded={isOpen}`
  - `aria-controls="addr-listbox"`
  - `aria-activedescendant={isOpen ? activeOptionDomId : undefined}`
  - `aria-labelledby="addr-picker-label"` (existing `<label>` for "Deliver to")
- Empty state (`value === null`): show a placeholder string from `t("fallbackLabel")` (existing key) in muted color.

### Listbox popover

Rendered when `isOpen === true`. Anchored beneath the trigger; CSS positions it absolutely within `.picker`.

```
┌────────────────────────────────────────────┐
│ ✓ Home    123 Main St, Mumbai 400001       │
│   Work    45 MG Rd, Bandra 400050          │
│ ─────────────────────────────────────────── │
│ Outside delivery area                       │
│   Office  Sector 1, Pune       [Outside]   │
│   Mom2    Sector 9, Navi       [Outside]   │
└────────────────────────────────────────────┘
```

- Attributes:
  - `<ul role="listbox" id="addr-listbox" tabIndex={-1}>`
  - Owned-by relationship via trigger's `aria-controls`.

### Row layout

```
[ ✓ ] [ Label    ] [ Formatted address (truncated) ]      [ Badge? ]
```

- Selected indicator on the left (a `✓` glyph or a filled circle) for the currently-selected `<li aria-selected="true">`. Hidden on others.
- Label column: medium-weight, takes its natural width.
- Address column: flexible, ellipsised.
- Badge: rendered only on outside-area rows. Compact pill with `tAddress("outsideAreaBadge")` text.

Each row:

```html
<li
  role="option"
  id="addr-opt-{id}"
  aria-selected={isSelected}
  aria-disabled={!serviceable}
  className={selected ? styles.optionSelected : ""}
  data-active={isActive ? "true" : undefined}
  onClick={…}
  onMouseEnter={…}
>
  {selected && <span aria-hidden="true">✓</span>}
  <span className={styles.optionLabel}>{label}</span>
  <span className={styles.optionAddress}>{address}</span>
  {!serviceable && <span className={styles.optionBadge}>{tAddress("outsideAreaBadge")}</span>}
</li>
```

### Section header for outside-area

Rendered only when at least one address is outside the radius (`hasOutsideArea === true`).

```html
<li role="presentation" className={styles.sectionHeader}>
  {tAddress("outsideDeliveryAreaHeader")}
</li>
```

- `role="presentation"` so screen readers skip it during option enumeration (the `aria-disabled` rows already announce their disabled state).
- Visually a small uppercase / muted text divider above the disabled rows.

### Sorting rules

The picker derives a single visible-order list each render:

1. **Deliverable group** (rendered first, in this order):
   - The single `is_default === true` address (if any and serviceable)
   - Other serviceable addresses in profile order
2. **Outside-area group** (rendered after the section header, in profile order)

Sorting is stable. If `storeId` is undefined (picker used outside checkout), no row is marked disabled and no section header renders.

## State and refs

Inside `AddressPicker.tsx`, add to the existing component:

```ts
const [isOpen, setIsOpen] = useState(false);
const [activeIndex, setActiveIndex] = useState(0);
const triggerRef = useRef<HTMLButtonElement | null>(null);
const listboxRef = useRef<HTMLUListElement | null>(null);
```

Derive each render:

```ts
const visibleOptions: { id: number; selectable: boolean }[] = useMemo(
  () => [
    ...deliverableOrdered.map((a) => ({ id: a.id, selectable: true })),
    ...outsideAreaOrdered.map((a) => ({ id: a.id, selectable: false })),
  ],
  [deliverableOrdered, outsideAreaOrdered],
);
```

`activeIndex` is an index into `visibleOptions`. The combobox displays a focus ring (`data-active="true"`) on the `<li>` at that index.

## Behaviour

### Opening

- Click on trigger toggles `isOpen`.
- On open: set `activeIndex` to the index of the currently-selected option, or to the first selectable option if no selection. Never start on a disabled row.
- Focus stays on the trigger; we never move DOM focus into the listbox (we use `aria-activedescendant` instead).

### Closing

- Click on document outside `.picker` → close. Implemented via a `mousedown` listener installed when `isOpen === true` and torn down on `false` or unmount.
- Escape key (on the trigger) → close and keep focus on trigger.
- Tab on the trigger → browser advances focus naturally; we close in a `blur` handler with a small `relatedTarget` check to ignore mouse-down-then-mouse-up sequences inside the listbox.
- Selecting an option (click or Enter / Space) → close, focus trigger.

### Keyboard navigation (handler on the trigger button)

- ArrowDown: move `activeIndex` to the next selectable option, wrapping to the first if at the end. If listbox closed, also open it.
- ArrowUp: move to the previous selectable option, wrapping to the last selectable one.
- Home: move to the first selectable option.
- End: move to the last selectable option.
- Enter or Space: if `visibleOptions[activeIndex].selectable === true`, call `onChange(visibleOptions[activeIndex].id)` and close. Otherwise no-op.
- Escape: close and focus the trigger.

Disabled rows are skipped during navigation; we never land the focus ring on them.

### Mouse interaction (per row)

- Selectable row click: `onChange(id)` + close.
- Disabled row click: no-op. CSS `cursor: not-allowed`.
- `onMouseEnter` on any row: set `activeIndex` to that row's index. (Disabled rows still update `activeIndex` for visual feedback, but Enter does not select them.) Actually no — we should not move active onto disabled rows even on mouse-enter, because then keyboard Enter could fire on the wrong row if the user mixed mouse + keyboard. **Rule:** `onMouseEnter` only updates `activeIndex` if the row is selectable.

### Scrolling

After `activeIndex` changes via keyboard, scroll the active `<li>` into view inside the scrollable listbox using `scrollIntoView({ block: "nearest" })`. Mouse-driven `activeIndex` updates do not scroll (the row is already on screen).

## Translation keys

Add to all five locale files (`messages/{en,hi,mr,gu,pa}.json`) under the existing `Address` namespace:

| Key | English value |
|-----|---------------|
| `outsideDeliveryAreaHeader` | "Outside delivery area" |
| `outsideAreaBadge` | "Outside area" |

The hardcoded `" (Outside delivery area)"` string is removed from `AddressPicker.tsx`. Non-English locales receive English-string placeholders if a native translation is not immediately available — the rest of the app already accepts that pattern (per CLAUDE.md and the existing locale workflow). Authoritative translations can land in a follow-up i18n pass.

## Files touched

- `frontend/src/components/orders/AddressPicker.tsx` — replace the `<select>...<option>...</select>` JSX with a `<button>` + `<ul role="listbox">` structure, add the state, refs, document listener `useEffect`, and key handlers.
- `frontend/src/components/orders/AddressPicker.module.css` — new classes: `.combo`, `.comboTrigger`, `.comboChevron`, `.listbox`, `.option`, `.optionSelected`, `.optionLabel`, `.optionAddress`, `.optionBadge`, `.sectionHeader`, `.placeholder`. Reuse design tokens (`--color-primary-1`, `--shade-cool-light-6`, `--radius-card`, etc.). Keep the existing `.picker`, `.header`, `.label`, `.addBtn`, `.empty`, `.emptyActions`, `.modalBody`, `.modalField`, `.modalInput`, `.modalCheckboxRow`, `.modalActions`, `.modalError`.
- `frontend/messages/{en,hi,mr,gu,pa}.json` — add the two `Address.*` keys.

## Edge cases

- **All addresses outside area** (`!hasAnyServiceable`): handled by the existing branch that renders the `noServiceableTitle` empty state + "Add address" button. The combobox is not rendered.
- **No addresses** (`addresses.length === 0`): handled by the existing empty-state branch.
- **Serviceability still loading** (`!allSettled`): combobox renders normally but no row is marked `aria-disabled` (the existing serviceability map keys are not yet populated). Outside-area section header is not rendered until at least one address is known to be out-of-radius. The checkout page's place-order button continues to disable via `pickerState.loading`.
- **Combobox open, address-modal opens on top via "+ Add address"**: opening the modal does not need to close the listbox explicitly because the `<Modal>` traps focus and the document-mousedown listener will fire on backdrop click. Defensive: close the listbox when `addModalOpen` flips true.
- **Long labels / addresses**: each row uses `min-width: 0` + `text-overflow: ellipsis` to truncate the address line. Label has a max-width to avoid pushing the address off-screen.
- **Single address only**: no section header renders (its array is empty). The single row appears as the only option.
- **storeId undefined** (picker used outside checkout): no serviceability checks run, no row is disabled, no outside-area section renders.

## Accessibility checklist

- `role="combobox"` on trigger, `role="listbox"` on `<ul>`, `role="option"` on `<li>`.
- `aria-haspopup="listbox"`, `aria-expanded`, `aria-controls`, `aria-activedescendant` on trigger.
- `aria-selected` on the currently-selected option; `aria-disabled="true"` on outside-area options.
- Section header uses `role="presentation"` so screen readers do not announce it as an option.
- Keyboard parity with native `<select>`: ArrowUp / ArrowDown / Home / End / Enter / Space / Escape.
- Focus remains on the trigger; `aria-activedescendant` shifts the "virtual focus" reported to assistive tech without moving DOM focus.
- Touch targets meet WCAG (each `<li>` is at least 44 × 44 CSS pixels).
- Existing `<label for="address-picker">` is updated to `<label id="addr-picker-label">` and the trigger references it via `aria-labelledby`. (Native-`<select>`-specific `htmlFor` is removed because there is no longer a `<select>` element to associate with.)

## Risks

- **Document mousedown listener cleanup.** Effect must remove the listener when `isOpen` becomes false or the component unmounts; missing cleanup causes wasted handler calls but no functional bug.
- **Tab-out edge case.** When the user presses Tab on the trigger while the listbox is open, browsers move focus to the next focusable element. The trigger's `blur` handler should close the listbox unless the new focus is inside `.picker` (interaction with the Add-Address button or the modal). Use `event.relatedTarget` against a ref containing both.
- **Mobile zoom on focus.** The trigger is a `<button>`, not an `<input>`, so iOS will not auto-zoom. Confirmed via the `<button>` element type.
- **Outside-area list growth.** A customer with many out-of-radius addresses (e.g., relatives in other cities) sees a long disabled section. The listbox has `max-height: 320px` + `overflow-y: auto` and scrolls naturally.
- **React 19 strict mode (Next.js dev).** Effect that adds the document listener runs twice in dev; the cleanup runs in between, so net listener count is correct. Verified by pattern (same approach used by `Modal.tsx`).

## Manual verification checklist (post-implementation)

1. Log in as a customer with at least one in-radius and one out-of-radius saved address. Reach a checkout page.
2. Confirm trigger renders the selected address on a single line with a chevron.
3. Click trigger — listbox opens beneath. Deliverable addresses appear first; "Outside delivery area" header + greyed rows appear below.
4. Each outside-area row shows an "Outside area" pill on the right.
5. Click an outside-area row — nothing happens; listbox stays open; cursor shows `not-allowed`.
6. Click a deliverable row — selected; listbox closes; trigger updates.
7. Press ArrowDown / ArrowUp — focus ring moves only across deliverable rows; outside-area rows are skipped.
8. Press Home / End — jumps to first / last deliverable row.
9. Press Enter on a deliverable active row — selects; closes.
10. Press Escape — closes; trigger retains focus.
11. Click outside the picker — closes.
12. Tab off the trigger — closes.
13. Repeat in each of `en`, `hi`, `mr`, `gu`, `pa` — header + pill render localized strings (or English fallbacks where translations are stub).
14. Screen reader (VoiceOver / NVDA / TalkBack): announces "Combobox, Home — 123 Main St…, collapsed". On open: "Listbox, 5 options". Arrow keys: "Home, selected" → "Work" → skip → … Disabled rows are announced as such.
15. Mobile (≤ 360px width): trigger fits without horizontal scroll; listbox doesn't overflow viewport; touch targets feel large enough.

## Out-of-scope follow-ups

- Authoritative translations for `outsideDeliveryAreaHeader` + `outsideAreaBadge` in hi / mr / gu / pa (separate i18n PR).
- Optional distance label on outside-area rows if customers later report confusion.
- Extracting the combobox into a generic `<Combobox>` if a second use case appears.
