# Admin Responsive + Light Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every page in `frontend/src/app/admin/**` work cleanly on mobile (`<480px`), tablet (`480–1024px`), and desktop, with consistent spacing, badges, buttons, and shadows.

**Architecture:** CSS-only changes to per-page `.module.css` files plus one additive prop on the shared `DataTable` component (mobile card render). No backend, no routing changes. Existing design tokens are reused; the global `768px` breakpoint stays canonical and `480px` is added where mobile-S diverges.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript, CSS Modules, design tokens in `frontend/src/styles/design-tokens.css`. No test framework wired on the frontend — verification is `npm run lint`, `npm run build`, and manual DevTools sweep at 375 / 414 / 768 / 1024 / 1440 px.

**Spec:** `docs/superpowers/specs/2026-05-03-admin-responsive-design.md`

**Branch:** `feat/admin-responsive` (already created and contains the spec commit).

---

## Pre-flight (one-time)

- [ ] **Step 1: Confirm branch and clean tree**

```bash
git status
git branch --show-current
```

Expected: branch is `feat/admin-responsive`. Spec commit `docs: spec for admin responsive + light polish` is the most recent.

- [ ] **Step 2: Confirm dev server runs**

In a separate terminal, from `frontend/`:

```bash
npm install
npm run dev
```

Open `http://localhost:3000/admin` and log in as admin to confirm the existing dashboard renders. Leave the server running through the rest of the plan.

---

## Task 1: DataTable mobile card mode (additive)

**Files:**
- Modify: `frontend/src/components/DataTable.tsx`
- Modify: `frontend/src/components/DataTable.module.css`

**Why first:** subsequent tasks depend on this prop existing.

- [ ] **Step 1: Add `mobileCardRender` prop and dual rendering**

Replace the entire contents of `frontend/src/components/DataTable.tsx` with:

```tsx
import styles from "./DataTable.module.css";

export interface Column<T> {
  key: string;
  label: string;
  render?: (row: T) => React.ReactNode;
}

interface Props<T> {
  columns: Column<T>[];
  data: T[];
  keyField: string;
  onEdit?: (row: T) => void;
  onDelete?: (row: T) => void;
  emptyMessage?: string;
  mobileCardRender?: (row: T) => React.ReactNode;
}

export default function DataTable<T extends object>({
  columns,
  data,
  keyField,
  onEdit,
  onDelete,
  emptyMessage = "No data to display",
  mobileCardRender,
}: Props<T>) {
  if (data.length === 0) {
    return (
      <div className={styles.tableWrap}>
        <div className={styles.empty}>
          <div className={styles.emptyIcon}>📋</div>
          <p className={styles.emptyText}>{emptyMessage}</p>
        </div>
      </div>
    );
  }

  const hasActions = Boolean(onEdit || onDelete);

  return (
    <div className={styles.tableWrap}>
      <table
        className={`${styles.table} ${mobileCardRender ? styles.tableHideOnMobile : ""}`}
      >
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key}>{col.label}</th>
            ))}
            {hasActions && <th>Actions</th>}
          </tr>
        </thead>
        <tbody>
          {data.map((row) => {
            const rec = row as Record<string, unknown>;
            return (
              <tr key={String(rec[keyField])}>
                {columns.map((col) => (
                  <td key={col.key}>
                    {col.render
                      ? col.render(row)
                      : String(rec[col.key] ?? "—")}
                  </td>
                ))}
                {hasActions && (
                  <td>
                    <div className={styles.actions}>
                      {onEdit && (
                        <button
                          className={`${styles.actionBtn} ${styles.editBtn}`}
                          onClick={() => onEdit(row)}
                        >
                          Edit
                        </button>
                      )}
                      {onDelete && (
                        <button
                          className={`${styles.actionBtn} ${styles.deleteBtn}`}
                          onClick={() => onDelete(row)}
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>

      {mobileCardRender && (
        <div className={styles.mobileCardList}>
          {data.map((row) => {
            const rec = row as Record<string, unknown>;
            return (
              <div className={styles.mobileCard} key={String(rec[keyField])}>
                {mobileCardRender(row)}
                {hasActions && (
                  <div className={styles.mobileCardActions}>
                    {onEdit && (
                      <button
                        className={`${styles.actionBtn} ${styles.editBtn}`}
                        onClick={() => onEdit(row)}
                      >
                        Edit
                      </button>
                    )}
                    {onDelete && (
                      <button
                        className={`${styles.actionBtn} ${styles.deleteBtn}`}
                        onClick={() => onDelete(row)}
                      >
                        Delete
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add card-mode CSS**

Replace the contents of `frontend/src/components/DataTable.module.css` with:

```css
.tableWrap {
  background: var(--color-neutral-0);
  border: 1px solid var(--color-neutral-100);
  border-radius: var(--radius-xl);
  overflow: hidden;
}

.table {
  width: 100%;
  border-collapse: collapse;
}

.table th {
  padding: var(--space-3) var(--space-4);
  font-size: var(--font-xs);
  font-weight: var(--weight-semibold);
  color: var(--color-neutral-500);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wider);
  text-align: left;
  background: var(--color-neutral-50);
  border-bottom: 1px solid var(--color-neutral-100);
  white-space: nowrap;
  user-select: none;
}

.table td {
  padding: var(--space-3) var(--space-4);
  font-size: var(--font-sm);
  color: var(--color-neutral-700);
  border-bottom: 1px solid var(--color-neutral-50);
  vertical-align: middle;
}

.table tr:last-child td {
  border-bottom: none;
}

.table tbody tr {
  transition: background var(--duration-fast) var(--ease-default);
}

.table tbody tr:hover {
  background: var(--color-neutral-50);
}

/* ── Actions column ──────────────── */
.actions {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.actionBtn {
  padding: var(--space-1-5) var(--space-2);
  font-size: var(--font-xs);
  font-weight: var(--weight-medium);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-default);
  min-height: 36px;
}

.editBtn {
  color: var(--color-primary-500);
  background: var(--color-primary-50);
}

.editBtn:hover {
  background: var(--color-primary-100);
}

.deleteBtn {
  color: var(--color-error);
  background: hsla(0, 84%, 60%, 0.08);
}

.deleteBtn:hover {
  background: hsla(0, 84%, 60%, 0.15);
}

/* ── Empty state ─────────────────── */
.empty {
  text-align: center;
  padding: var(--space-12) var(--space-4);
  color: var(--color-neutral-400);
}

.emptyIcon {
  font-size: 48px;
  margin-bottom: var(--space-3);
  opacity: 0.5;
}

.emptyText {
  font-size: var(--font-sm);
}

/* ── Status pill ─────────────────── */
.statusPill {
  display: inline-flex;
  align-items: center;
  padding: var(--space-0-5) var(--space-2);
  font-size: var(--font-xs);
  font-weight: var(--weight-medium);
  border-radius: var(--radius-full);
}

.statusAvailable {
  background: var(--color-accent-50);
  color: var(--color-accent-600);
}

.statusUnavailable {
  background: hsla(0, 84%, 60%, 0.1);
  color: var(--color-error);
}

/* ── Mobile card list (opt-in) ─────── */
.mobileCardList {
  display: none;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-2);
  background: var(--color-neutral-50);
}

.mobileCard {
  background: var(--color-neutral-0);
  border: 1px solid var(--color-neutral-100);
  border-radius: var(--radius-lg);
  padding: var(--space-3) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  box-shadow: var(--shadow-sm);
}

.mobileCardActions {
  display: flex;
  gap: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px solid var(--color-neutral-100);
}

.mobileCardActions .actionBtn {
  flex: 1;
  min-height: 44px;
  padding: var(--space-2) var(--space-3);
  font-size: var(--font-sm);
}

/* ── Responsive ──────────────────── */
@media (max-width: 768px) {
  .tableWrap {
    overflow-x: auto;
  }

  .table:not(.tableHideOnMobile) {
    min-width: 600px;
  }

  .tableHideOnMobile {
    display: none;
  }

  .mobileCardList {
    display: flex;
  }
}
```

- [ ] **Step 3: Verify type-check passes**

From `frontend/`:

```bash
npm run lint
```

Expected: zero errors. (Existing pages don't pass `mobileCardRender`, so they keep the table-with-scroll path.)

- [ ] **Step 4: Visual smoke test**

Open `http://localhost:3000/admin/products` in DevTools. Toggle device toolbar at 375px. Confirm the table still scrolls horizontally (no card mode yet — Task 3 wires it).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DataTable.tsx frontend/src/components/DataTable.module.css
git commit -m "feat(admin): add mobile card mode to DataTable"
```

---

## Task 2: Categories page card mode

**Files:**
- Modify: `frontend/src/app/admin/categories/page.tsx`
- Modify: `frontend/src/app/admin/products/page.module.css` (only if shared toolbar styles need a new mobile-S rule)

The categories page reuses `products/page.module.css` for `toolbar`, `toolbarLeft`, `toolbarCount`, `filterSelect`, `addBtn`, `categoryBadge`. Toolbar is already `flex-wrap: wrap`. We need (a) full-width add button on `<480px`, (b) `mobileCardRender` prop added to the DataTable call.

- [ ] **Step 1: Read the page so you know what data shape is rendered**

```bash
sed -n '1,200p' frontend/src/app/admin/categories/page.tsx
```

Note the Category fields used in the existing column renders (typically `name`, `service`, `description`, plus a `product_count` if present). Use only fields that exist in current columns.

- [ ] **Step 2: Pass `mobileCardRender` to the DataTable**

In `frontend/src/app/admin/categories/page.tsx`, locate the `<DataTable ... />` JSX and add the new prop. The card layout should mirror what columns currently show. Example shape (adapt field names to whatever the current columns use):

```tsx
<DataTable
  columns={columns}
  data={categories}
  keyField="id"
  onEdit={(c) => openEdit(c)}
  onDelete={(c) => handleDelete(c)}
  emptyMessage="No categories yet"
  mobileCardRender={(c) => (
    <>
      <div className={mobileStyles.cardTopRow}>
        <span className={mobileStyles.cardTitle}>{c.name}</span>
        <span className={pageStyles.categoryBadge}>{c.service}</span>
      </div>
      {c.description && (
        <p className={mobileStyles.cardSubtitle}>{c.description}</p>
      )}
      {typeof c.product_count === "number" && (
        <div className={mobileStyles.cardMeta}>
          {c.product_count} product{c.product_count === 1 ? "" : "s"}
        </div>
      )}
    </>
  )}
/>
```

- [ ] **Step 3: Create a small co-located CSS module for shared mobile-card text styles**

Because categories, products, and sellers all need the same card title / subtitle / meta typography, create one shared file:

Create `frontend/src/components/DataTableCard.module.css`:

```css
.cardTopRow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.cardTitle {
  font-size: var(--font-sm);
  font-weight: var(--weight-semibold);
  color: var(--color-neutral-900);
  word-break: break-word;
}

.cardPriceRight {
  font-size: var(--font-sm);
  font-weight: var(--weight-semibold);
  color: var(--color-neutral-900);
  flex-shrink: 0;
}

.cardSubtitle {
  font-size: var(--font-xs);
  color: var(--color-neutral-500);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin: 0;
}

.cardMeta {
  font-size: var(--font-xs);
  color: var(--color-neutral-400);
}

.cardChips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}
```

- [ ] **Step 4: Import the shared card styles in categories page**

At the top of `frontend/src/app/admin/categories/page.tsx`, add:

```ts
import mobileStyles from "@/components/DataTableCard.module.css";
```

(Keep the existing `pageStyles` import that points to products `page.module.css`.)

- [ ] **Step 5: Add mobile-S toolbar rule**

In `frontend/src/app/admin/products/page.module.css`, append:

```css
@media (max-width: 480px) {
  .toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .toolbarLeft {
    flex-wrap: wrap;
  }

  .addBtn {
    width: 100%;
    justify-content: center;
    min-height: 44px;
  }

  .filterSelect {
    flex: 1;
    min-height: 44px;
  }
}
```

- [ ] **Step 6: Lint + visual check**

```bash
npm run lint
```

In DevTools at 375px, open `http://localhost:3000/admin/categories`. Confirm:
- Cards stack vertically, no horizontal scroll on `<body>`.
- Edit and Delete buttons are full-width at the bottom of each card.
- Add button spans full width below filter select.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/DataTableCard.module.css \
        frontend/src/app/admin/categories/page.tsx \
        frontend/src/app/admin/products/page.module.css
git commit -m "feat(admin): mobile card view for categories + responsive toolbar"
```

---

## Task 3: Products page card mode

**Files:**
- Modify: `frontend/src/app/admin/products/page.tsx`

- [ ] **Step 1: Read page to find current column fields**

```bash
sed -n '1,200p' frontend/src/app/admin/products/page.tsx
```

Spec card layout: top row = name + base_price (right-aligned), subtitle = category badge + description (clamped 2 lines).

- [ ] **Step 2: Add import + `mobileCardRender`**

Add at the top of `frontend/src/app/admin/products/page.tsx`:

```ts
import mobileStyles from "@/components/DataTableCard.module.css";
```

In the `<DataTable ... />` call, add (adapt field names to actual `MasterProduct` shape — typically `name`, `base_price`, `category` or `category_name`, `description`):

```tsx
mobileCardRender={(p) => (
  <>
    <div className={mobileStyles.cardTopRow}>
      <span className={mobileStyles.cardTitle}>{p.name}</span>
      <span className={mobileStyles.cardPriceRight}>
        ₹{Number(p.base_price ?? 0).toFixed(2)}
      </span>
    </div>
    <div className={mobileStyles.cardChips}>
      <span className={pageStyles.categoryBadge}>
        {p.category_name ?? p.category ?? "—"}
      </span>
    </div>
    {p.description && (
      <p className={mobileStyles.cardSubtitle}>{p.description}</p>
    )}
  </>
)}
```

If the existing import name for the products `page.module.css` styles is not `pageStyles`, keep whatever name the file currently uses and update the snippet above accordingly.

- [ ] **Step 3: Lint + visual check**

```bash
npm run lint
```

DevTools at 375px on `/admin/products`. Confirm price is right-aligned, category chip shows under the title, description is 2-line clamped.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/admin/products/page.tsx
git commit -m "feat(admin): mobile card view for products"
```

---

## Task 4: Sellers page card mode + review modal grid

**Files:**
- Modify: `frontend/src/app/admin/sellers/page.tsx`
- Modify: `frontend/src/app/admin/sellers/page.module.css`

- [ ] **Step 1: Read page to find seller-application shape**

```bash
sed -n '1,260p' frontend/src/app/admin/sellers/page.tsx
```

Note the fields rendered in current columns: `business_name`, `owner_name`, `owner_email`, `services`, `submitted_at`, `status`. Use those.

- [ ] **Step 2: Add import + `mobileCardRender`**

Top of `frontend/src/app/admin/sellers/page.tsx`:

```ts
import mobileStyles from "@/components/DataTableCard.module.css";
```

In the `<DataTable ... />` call, add (adapt field names):

```tsx
mobileCardRender={(app) => (
  <>
    <div className={mobileStyles.cardTopRow}>
      <span className={mobileStyles.cardTitle}>{app.business_name}</span>
      <span className={`${pageStyles.statusPill} ${pageStyles[`status${app.status[0].toUpperCase()}${app.status.slice(1)}`]}`}>
        {app.status}
      </span>
    </div>
    <div className={pageStyles.ownerCell}>
      <span>{app.owner_name}</span>
      <span className={pageStyles.ownerEmail}>{app.owner_email}</span>
    </div>
    <div className={mobileStyles.cardMeta}>
      {(app.services?.length ?? 0)} service{app.services?.length === 1 ? "" : "s"}
      {app.submitted_at && ` • ${new Date(app.submitted_at).toLocaleDateString()}`}
    </div>
    <button
      className={pageStyles.reviewBtn}
      style={{ width: "100%", minHeight: 44 }}
      onClick={() => openReview(app)}
    >
      Review
    </button>
  </>
)}
```

If the existing import name for sellers `page.module.css` styles is not `pageStyles`, use the actual name. Replace `openReview(app)` with whatever handler the page uses to open the review modal.

Because the row already has its own Review button, do NOT pass `onEdit` / `onDelete`. The card actions footer must stay empty — verify the page does not currently pass `onEdit` / `onDelete` to this DataTable. (If it does, leave them, and remove the inline Review button from `mobileCardRender` to avoid duplication.)

- [ ] **Step 3: Make tabs scroll-x and detailsGrid stack**

Append to `frontend/src/app/admin/sellers/page.module.css`:

```css
@media (max-width: 768px) {
  .tabs {
    overflow-x: auto;
    flex-wrap: nowrap;
    scrollbar-width: none;
    -ms-overflow-style: none;
  }

  .tabs::-webkit-scrollbar {
    display: none;
  }

  .tab {
    flex-shrink: 0;
  }

  .detailsGrid {
    grid-template-columns: 1fr;
    gap: 1rem;
  }

  .reviewBtn {
    min-height: 44px;
  }

  .successBtn,
  .dangerBtn {
    min-height: 44px;
    width: 100%;
  }
}

@media (max-width: 480px) {
  .toolbar {
    flex-direction: column;
    align-items: stretch;
  }
}
```

- [ ] **Step 4: Lint + visual check**

```bash
npm run lint
```

At 375px on `/admin/sellers`:
- Cards show business + status, owner block, meta line, full-width Review button.
- Tabs scroll horizontally without wrapping.
- Open the Review modal: details collapse to a single column, action buttons are full-width.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/admin/sellers/page.tsx \
        frontend/src/app/admin/sellers/page.module.css
git commit -m "feat(admin): mobile card view for sellers + responsive review modal"
```

---

## Task 5: Orders list page responsive

**Files:**
- Modify: `frontend/src/app/admin/orders/page.module.css`

The list page uses CSS-Module classes only — no JSX changes needed.

- [ ] **Step 1: Replace the file contents**

Overwrite `frontend/src/app/admin/orders/page.module.css` with:

```css
.page {
  padding: 1.5rem;
  max-width: 1100px;
  margin: 0 auto;
}

.title {
  font-size: 1.6rem;
  margin-bottom: 1rem;
}

.tabs {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

.tab,
.tabActive {
  border: 1px solid var(--color-border, #d1d5db);
  background: transparent;
  padding: 0.5rem 1rem;
  border-radius: 999px;
  cursor: pointer;
  font-weight: 500;
  min-height: 36px;
}

.tabActive {
  background: var(--color-primary, #16a34a);
  color: white;
  border-color: transparent;
}

.empty {
  color: var(--color-text-muted, #6b7280);
  padding: 2rem;
  text-align: center;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}

@media (max-width: 768px) {
  .page {
    padding: 1rem;
  }

  .title {
    font-size: 1.4rem;
  }

  .tabs {
    overflow-x: auto;
    flex-wrap: nowrap;
    scrollbar-width: none;
    -ms-overflow-style: none;
  }

  .tabs::-webkit-scrollbar {
    display: none;
  }

  .tab,
  .tabActive {
    flex-shrink: 0;
    min-height: 44px;
  }
}

@media (max-width: 480px) {
  .page {
    padding: 0.75rem;
  }

  .grid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 2: Lint + visual check**

```bash
npm run lint
```

At 375px on `/admin/orders`:
- No horizontal page scroll.
- Tabs scroll horizontally on overflow, no wrap.
- Order cards are full-width.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/admin/orders/page.module.css
git commit -m "feat(admin): responsive orders list page"
```

---

## Task 6: Order detail page responsive

**Files:**
- Modify: `frontend/src/app/admin/orders/[id]/page.module.css`

- [ ] **Step 1: Replace the file contents**

Overwrite `frontend/src/app/admin/orders/[id]/page.module.css` with:

```css
.page {
  padding: 1.5rem;
  max-width: 800px;
  margin: 0 auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.title {
  font-size: 1.6rem;
  margin: 0;
}

.subtitle {
  color: var(--color-text-muted, #6b7280);
  margin-top: 0.25rem;
}

.section {
  margin-top: 1.5rem;
  padding: 1rem;
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 10px;
}

.sectionTitle {
  font-size: 1.05rem;
  margin: 0 0 0.6rem;
}

.totals {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin-top: 0.8rem;
  font-variant-numeric: tabular-nums;
}

.totals div {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.grand {
  font-weight: 700;
  font-size: 1.1rem;
  border-top: 1px solid var(--color-border, #e5e7eb);
  padding-top: 0.4rem;
  margin-top: 0.3rem;
}

.loading,
.error {
  padding: 2rem;
  text-align: center;
  color: var(--color-text-muted, #6b7280);
}

.error {
  color: #991b1b;
}

@media (max-width: 768px) {
  .page {
    padding: 1rem;
  }

  .title {
    font-size: 1.4rem;
  }

  .header {
    align-items: flex-start;
  }

  .section {
    padding: 0.85rem;
  }
}

@media (max-width: 480px) {
  .page {
    padding: 0.75rem;
  }

  .totals div {
    flex-direction: row;
  }
}
```

- [ ] **Step 2: Make order action buttons stack on small screens**

Read `frontend/src/components/orders/OrderActionButtons.module.css` to see current layout:

```bash
sed -n '1,200p' frontend/src/components/orders/OrderActionButtons.module.css
```

Append to that file:

```css
@media (max-width: 640px) {
  .row,
  .actions,
  .container {
    flex-direction: column;
    align-items: stretch;
  }

  .row > button,
  .actions > button,
  .container > button {
    width: 100%;
    min-height: 44px;
  }
}
```

If the actual class names are different (e.g. only `.buttons` exists), substitute the real class name — keep the rule intent: stack to column, full width, 44px min-height under 640px. Do NOT add rules for class names that don't exist.

- [ ] **Step 3: Lint + visual check**

```bash
npm run lint
```

At 375px on `/admin/orders/<some-id>`:
- Header title and status badge wrap onto separate lines without overlap.
- Action buttons stack full-width.
- Totals rows still align label/value.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/admin/orders/[id]/page.module.css \
        frontend/src/components/orders/OrderActionButtons.module.css
git commit -m "feat(admin): responsive order detail page"
```

---

## Task 7: Dashboard + shared seller styles polish

**Files:**
- Modify: `frontend/src/app/seller/page.module.css` (shared with admin dashboard via the import in `frontend/src/app/admin/page.tsx:11`)
- Modify: `frontend/src/components/StatsCard.module.css`

This file is shared with the seller dashboard. Changes must improve both, not regress the seller side. The rules added here are additive media queries, so the desktop layout is unchanged.

- [ ] **Step 1: Append responsive rules to `seller/page.module.css`**

Append to `frontend/src/app/seller/page.module.css`:

```css
@media (max-width: 768px) {
  .statsGrid {
    grid-template-columns: repeat(2, 1fr);
    gap: var(--space-3);
    margin-bottom: var(--space-6);
  }

  .quickActions {
    gap: var(--space-2);
  }

  .actionCard {
    flex: 1 1 100%;
    min-width: 0;
  }
}

@media (max-width: 480px) {
  .statsGrid {
    grid-template-columns: 1fr;
  }

  .sectionHeader {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-2);
  }
}
```

- [ ] **Step 2: Append responsive rules to `StatsCard.module.css`**

Append to `frontend/src/components/StatsCard.module.css`:

```css
@media (max-width: 480px) {
  .card {
    padding: var(--space-4);
    gap: var(--space-3);
  }

  .iconWrap {
    width: 40px;
    height: 40px;
    font-size: var(--font-xl);
  }

  .value {
    font-size: var(--font-xl);
  }
}
```

- [ ] **Step 3: Lint + visual check**

```bash
npm run lint
```

At 375px on `/admin`:
- Stats cards are 1 column, with smaller icon and number.
- Quick action cards span full width and stack vertically.
- Section headers wrap label and (any) trailing control onto two lines.

Also verify `/seller` (if accessible to your account) still looks correct on desktop and mobile — same rules apply there.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/seller/page.module.css \
        frontend/src/components/StatsCard.module.css
git commit -m "feat(admin): responsive dashboard stats grid and quick actions"
```

---

## Task 8: Dashboard layout polish + final sweep

**Files:**
- Modify: `frontend/src/components/DashboardLayout.module.css`

- [ ] **Step 1: Tighten top bar and improve touch targets at small widths**

Append to `frontend/src/components/DashboardLayout.module.css`:

```css
@media (max-width: 768px) {
  .topBar {
    padding: var(--space-3) var(--space-4);
  }

  .topBarTitle {
    font-size: var(--font-lg);
  }

  .sidebarLink {
    min-height: 44px;
  }

  .mobileToggle {
    width: 44px;
    height: 44px;
  }
}

@media (max-width: 480px) {
  .content {
    padding: var(--space-3);
  }

  .topBarActions {
    gap: var(--space-2);
  }
}
```

- [ ] **Step 2: Final cross-page sweep**

In DevTools at 375 / 414 / 768 / 1024 / 1440 px, walk through:
- `/admin` (dashboard)
- `/admin/orders`
- `/admin/orders/<id>` (open one)
- `/admin/sellers` (open the Review modal on at least one application)
- `/admin/products` (open the Add and Edit modals)
- `/admin/categories` (open the Add and Edit modals)

Confirm at every viewport:
- No horizontal scroll on `<body>`.
- All primary CTAs are reachable and at least 44px tall on mobile.
- Modals fit within viewport (no clipped buttons).
- No overlapping text or icons.
- Sidebar opens/closes from hamburger; overlay dims background.

If a regression is found, fix it in the relevant `*.module.css` and commit with `fix(admin): <describe>`.

- [ ] **Step 3: Build to confirm production output is clean**

From `frontend/`:

```bash
npm run lint
npm run build
```

Expected: lint exit code 0, build completes with no errors. Warnings about pre-existing issues unrelated to this branch may be ignored — note them in the PR description if you see any.

- [ ] **Step 4: Commit any final polish from Step 2 plus this layout change**

```bash
git add frontend/src/components/DashboardLayout.module.css
git commit -m "feat(admin): polish dashboard layout for mobile"
```

---

## Done

Final state:
- `feat/admin-responsive` branch contains: spec commit + 7 implementation commits (one per Task 1–7) + optional polish commit (Task 8).
- All admin pages render cleanly at every tested breakpoint.
- DataTable retains its previous behavior on pages that did not opt into card mode.

Do **not** open a PR. Per project policy, wait for explicit user permission.
