# Add Product Modal — Search + Always-Enabled Add — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make per-category `+ Add` buttons always clickable, and replace the modal's plain `<select>` with a searchable, scrollable product list.

**Architecture:** All changes are inside `frontend/src/app/(operator)/seller/inventory/page.tsx` and `page.module.css`. Add modal gains local `searchQuery` and `showAll` state, plus filter composition (preset → search). New CSS classes back the search input + product list.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript, CSS Modules. No new dependencies. Project has no frontend tests — verification is `npm run lint` + `npm run build` + manual browser checks.

**Spec:** `docs/superpowers/specs/2026-05-05-add-product-modal-search-design.md`

**Branch:** `feat/seller-inventory-grouped` (already checked out; spec already committed).

---

## Files Touched

- **Modify:** `frontend/src/app/(operator)/seller/inventory/page.tsx` — drop disable on per-category Add buttons, replace modal product `<select>` with searchable list, add `searchQuery` + `showAll` state, add empty-state messaging.
- **Modify:** `frontend/src/app/(operator)/seller/inventory/page.module.css` — `.searchInput`, `.productList`, `.productListRow`, `.productListRowSelected`, `.productListEmpty`, `.showAllBtn`.

No new files.

---

## Task 1: Always-enable per-category Add buttons

Drop the `disabled={...}` props on the per-category `+ Add` buttons (in the category header and in the empty-category placeholder). Global toolbar `+ Add Product` keeps its existing disabled prop.

**Files:**
- Modify: `frontend/src/app/(operator)/seller/inventory/page.tsx`

- [ ] **Step 1.1: Edit the per-category header `+ Add` button**

In `frontend/src/app/(operator)/seller/inventory/page.tsx`, replace this block:

```tsx
            <button
              className={styles.categoryAddBtn}
              onClick={() => openAdd(bucket.category.id)}
              disabled={
                availableProducts.filter((p) => p.category_id === bucket.category.id)
                  .length === 0
              }
            >
              + Add
            </button>
```

with:

```tsx
            <button
              className={styles.categoryAddBtn}
              onClick={() => openAdd(bucket.category.id)}
            >
              + Add
            </button>
```

- [ ] **Step 1.2: Edit the empty-placeholder `+ Add` button**

Replace this block:

```tsx
              <button
                className={styles.categoryAddBtn}
                style={{ marginLeft: "var(--space-2)" }}
                onClick={() => openAdd(bucket.category.id)}
                disabled={
                  availableProducts.filter((p) => p.category_id === bucket.category.id)
                    .length === 0
                }
              >
                + Add
              </button>
```

with:

```tsx
              <button
                className={styles.categoryAddBtn}
                style={{ marginLeft: "var(--space-2)" }}
                onClick={() => openAdd(bucket.category.id)}
              >
                + Add
              </button>
```

- [ ] **Step 1.3: Verify lint + build**

From `frontend/`:

```bash
npm run lint
npm run build
```

Expected: both clean.

- [ ] **Step 1.4: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/inventory/page.tsx
git commit -m "feat(seller): always allow per-category add product"
```

---

## Task 2: Add CSS classes for search input and product list

Append new classes to the page CSS module. They will be consumed by the modal rewrite in Task 3.

**Files:**
- Modify: `frontend/src/app/(operator)/seller/inventory/page.module.css`

- [ ] **Step 2.1: Append CSS rules**

Append the following to `frontend/src/app/(operator)/seller/inventory/page.module.css`, just above the `@media (max-width: 480px)` block:

```css
.searchInput {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  font-size: var(--font-sm);
  border: 1px solid var(--color-neutral-300);
  border-radius: var(--radius-md);
  background: var(--color-neutral-0);
}

.searchInput:focus {
  outline: none;
  border-color: var(--color-primary-400);
  box-shadow: 0 0 0 3px var(--color-primary-100);
}

.productList {
  max-height: 280px;
  overflow-y: auto;
  border: 1px solid var(--color-neutral-200);
  border-radius: var(--radius-md);
  background: var(--color-neutral-0);
}

.productListRow {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-neutral-100);
  cursor: pointer;
  font-size: var(--font-sm);
  color: var(--color-neutral-800);
  background: transparent;
  border-left: none;
  border-right: none;
  border-top: none;
  width: 100%;
  text-align: left;
  transition: background var(--duration-fast) var(--ease-default);
}

.productListRow:last-child {
  border-bottom: none;
}

.productListRow:hover {
  background: var(--color-neutral-50);
}

.productListRowSelected {
  background: var(--color-primary-50);
  color: var(--color-primary-800);
}

.productListRowSelected:hover {
  background: var(--color-primary-50);
}

.productListEmpty {
  padding: var(--space-4);
  text-align: center;
  color: var(--color-neutral-500);
  font-size: var(--font-sm);
  font-style: italic;
}

.showAllBtn {
  margin-top: var(--space-2);
  background: none;
  border: none;
  color: var(--color-primary-600);
  font-size: var(--font-sm);
  font-weight: var(--weight-medium);
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
}

.showAllBtn:hover {
  color: var(--color-primary-700);
}
```

- [ ] **Step 2.2: Verify lint + build**

```bash
npm run lint
npm run build
```

Expected: both clean. (No JSX consumes these classes yet — that's Task 3.)

- [ ] **Step 2.3: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/inventory/page.module.css
git commit -m "style(seller): add product search list styles"
```

---

## Task 3: Replace `<select>` with search + filtered list inside Add modal

Add `searchQuery` and `showAll` local state. Compute the visible list as `availableProducts → preset filter → search filter`. Render the search input + scrollable list. Handle three empty states (preset exhausted, search miss, store-wide exhausted). Auto-select first product when the visible list changes and the current selection isn't in it.

**Files:**
- Modify: `frontend/src/app/(operator)/seller/inventory/page.tsx`

- [ ] **Step 3.1: Add `searchQuery` and `showAll` state**

In the page component body, just below the `presetCategoryId` state declaration (line near `const [presetCategoryId, setPresetCategoryId] = useState<number | null>(null);`), add:

```tsx
const [searchQuery, setSearchQuery] = useState("");
const [showAll, setShowAll] = useState(false);
```

- [ ] **Step 3.2: Reset modal-local state when opening**

Replace the existing `openAdd` function:

```tsx
function openAdd(categoryId?: number) {
  const pool = categoryId
    ? availableProducts.filter((p) => p.category_id === categoryId)
    : availableProducts;
  setPresetCategoryId(categoryId ?? null);
  setFormProductId(pool[0]?.id ?? 0);
  setFormPrice("");
  setFormStock("");
  setSearchQuery("");
  setShowAll(false);
  setShowAdd(true);
}
```

Reset `searchQuery` and `showAll` when closing or completing too. Replace the modal `onClose` handler and Cancel button:

```tsx
onClose={() => {
  setShowAdd(false);
  setPresetCategoryId(null);
  setSearchQuery("");
  setShowAll(false);
}}
```

```tsx
<button
  className="btn btn-outline"
  onClick={() => {
    setShowAdd(false);
    setPresetCategoryId(null);
    setSearchQuery("");
    setShowAll(false);
  }}
>
  Cancel
</button>
```

In `handleAdd`, after the existing `setPresetCategoryId(null);` line, add:

```tsx
setSearchQuery("");
setShowAll(false);
```

- [ ] **Step 3.3: Compute the visible product list inside the modal JSX**

Inside the `{showAdd && (` Modal JSX, just above the `<div className={modalStyles.formGroup}>` for the product field, add:

```tsx
{(() => {
  // marker: visible list computation block — replaced in next step
  return null;
})()}
```

Wait — that's a placeholder. Skip Step 3.3; we compute the list inline in Step 3.4 by reshaping the modal body.

- [ ] **Step 3.4: Replace the modal body — Product field block**

Replace this entire JSX block:

```tsx
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Product</label>
            <select
              className={modalStyles.select}
              value={formProductId}
              onChange={(e) => setFormProductId(parseInt(e.target.value, 10))}
            >
              {availableProducts
                .filter((p) =>
                  presetCategoryId == null ? true : p.category_id === presetCategoryId
                )
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} — ₹{p.base_price}
                  </option>
                ))}
            </select>
          </div>
```

with:

```tsx
          {(() => {
            const presetActive = presetCategoryId !== null && !showAll;
            const presetPool = presetActive
              ? availableProducts.filter((p) => p.category_id === presetCategoryId)
              : availableProducts;
            const q = searchQuery.trim().toLowerCase();
            const visible = q
              ? presetPool.filter((p) => p.name.toLowerCase().includes(q))
              : presetPool;

            // Auto-select first visible product when current pick isn't in view.
            if (
              visible.length > 0 &&
              !visible.some((p) => p.id === formProductId)
            ) {
              // Defer to commit the new id without triggering a render-loop warning.
              queueMicrotask(() => setFormProductId(visible[0].id));
            }

            return (
              <div className={modalStyles.formGroup}>
                <label className={modalStyles.label}>Product</label>
                <input
                  type="search"
                  className={styles.searchInput}
                  placeholder="Search products…"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
                <div
                  className={styles.productList}
                  style={{ marginTop: "var(--space-2)" }}
                >
                  {visible.length === 0 ? (
                    <div className={styles.productListEmpty}>
                      {q
                        ? `No products match "${searchQuery}".`
                        : presetActive
                        ? (
                          <>
                            All products in this category are already in your inventory.
                            <br />
                            <button
                              type="button"
                              className={styles.showAllBtn}
                              onClick={() => setShowAll(true)}
                            >
                              Show all products
                            </button>
                          </>
                        )
                        : "All available products are already in your inventory."}
                    </div>
                  ) : (
                    visible.map((p) => {
                      const selected = p.id === formProductId;
                      return (
                        <button
                          type="button"
                          key={p.id}
                          className={`${styles.productListRow} ${
                            selected ? styles.productListRowSelected : ""
                          }`}
                          onClick={() => setFormProductId(p.id)}
                        >
                          <span>{p.name}</span>
                          <span style={{ color: "var(--color-neutral-500)" }}>
                            ₹{p.base_price}
                          </span>
                        </button>
                      );
                    })
                  )}
                </div>
              </div>
            );
          })()}
```

Notes:
- `queueMicrotask` defers `setFormProductId` to avoid the React "setState during render" warning. It runs once committed; if the user types fast, a single micro-task tail is fine.
- The empty-state handles all three cases per the spec's filter composition.
- The list is keyboard-clickable (each row is a `<button type="button">`).

- [ ] **Step 3.5: Disable `Add Product` footer button when nothing is selected**

In the modal `footer` block, replace:

```tsx
<button className="btn btn-primary" onClick={handleAdd}>Add Product</button>
```

with:

```tsx
<button
  className="btn btn-primary"
  onClick={handleAdd}
  disabled={!availableProducts.some((p) => p.id === formProductId)}
>
  Add Product
</button>
```

- [ ] **Step 3.6: Verify lint + build**

```bash
npm run lint
npm run build
```

Expected: both clean.

- [ ] **Step 3.7: Manual verification**

In `npm run dev`:

- Per-category `+ Add` buttons are always clickable.
- Modal opens with search input + scrollable list. Typing filters by name (case-insensitive substring).
- Per-category Add for a fully-stocked category shows "All products in this category are already in your inventory." with a "Show all products" link. Clicking the link reveals all available products.
- Search with no matches shows `No products match "<query>".`.
- Selecting a row highlights it; `Add Product` button enables.
- Save adds the row; modal closes; search/showAll/preset reset.
- Cancel resets the same state.
- Global `+ Add Product` (toolbar) opens with no preset (full list) and stays disabled only when the entire master catalog is exhausted.

- [ ] **Step 3.8: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/inventory/page.tsx
git commit -m "feat(seller): searchable product list in add product modal"
```

---

## Task 4: Push branch (PR awaits user approval)

- [ ] **Step 4.1: Push the branch**

```bash
git push origin feat/seller-inventory-grouped
```

(No `-u` needed — branch already tracks origin.)

- [ ] **Step 4.2: Open PR (after explicit user approval per project rules)**

Per `CLAUDE.md`: wait for explicit user approval before opening the PR. Once approved, update the existing single-edit PR (if open) or create one with the combined commits.

---

## Self-Review Notes

- **Spec coverage:**
  - Always-enable per-category Add — Task 1.
  - Search input + filtered list — Task 3.
  - Preset filter composition with search — Task 3.4 (`presetActive` + search filter).
  - Empty states (preset exhausted, search miss, store exhausted) — Task 3.4.
  - "Show all products" escape hatch — Task 3.4.
  - Auto-select first visible product — Task 3.4 via `queueMicrotask`.
  - CSS classes — Task 2.
- **Placeholder scan:** Step 3.3 was originally a marker; removed by collapsing into Step 3.4. All other steps contain concrete code.
- **Type consistency:** `searchQuery: string`, `showAll: boolean`, `presetCategoryId: number | null` — used consistently. `formProductId: number` continues to be 0 when nothing is selected, matching prior behaviour.
- **Edge case — `formProductId === 0`:** the auto-select branch only fires when the current id isn't in the visible list. With `0` as the initial id and a non-empty visible list, the id will be replaced. With an empty visible list, the Add Product button is disabled (Step 3.5 check).
