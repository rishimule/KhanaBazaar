<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Bulk Inventory Editor — Grouped by Service & Category — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat bulk inventory sheet with a service-tab + category-section layout: tabs at top, sticky category nav, one `BulkInventorySheet` instance per category (driven by `originalIndex` references back into the global `rows` array). Selection, save, and dirty state stay global.

**Architecture:** Modify `bulk/page.tsx` to fetch categories, bucket `rows` by `(service, category)`, and render service tabs / category nav / per-category sections. Refactor `BulkInventorySheet` to accept `Array<{row, originalIndex}>` instead of plain `SheetRow[]`, and to drop the `Service` and `Category` columns. Extend `EligibleProductPicker` with optional `initialServiceId` / `initialCategoryId` props for per-category presets. Active service synced to URL via `?service=<slug>`.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript, CSS Modules. No new dependencies. Project has no frontend tests — verification is `npm run lint` + `npm run build` + manual browser checks.

**Spec:** `docs/superpowers/specs/2026-05-05-bulk-inventory-grouped-design.md`

**Branch:** `feat/bulk-inventory-grouped` (already created; spec already committed).

---

## Files Touched

- **Modify:** `frontend/src/app/(operator)/seller/inventory/bulk/page.tsx` — bucketing, tabs, nav, per-category sections, picker preset wiring, fetch categories.
- **Modify:** `frontend/src/app/(operator)/seller/inventory/bulk/BulkInventorySheet.tsx` — accept `Array<{row, originalIndex}>`; drop service/category columns; null-return on empty.
- **Modify:** `frontend/src/app/(operator)/seller/inventory/bulk/EligibleProductPicker.tsx` — accept optional `initialServiceId` / `initialCategoryId`.
- **Modify:** `frontend/src/app/(operator)/seller/inventory/bulk/bulk.module.css` — add tab / nav / section / empty-category classes.

No new files. No backend changes.

---

## Task 1: Refactor `BulkInventorySheet` to use `originalIndex`

Make the sheet component agnostic of where its rows live in the global array. Drop the `Service` and `Category` columns now (the page rewrite in Task 3 swaps to grouped sections). Internal contract change only — page.tsx is updated alongside so it still compiles.

**Files:**
- Modify: `frontend/src/app/(operator)/seller/inventory/bulk/BulkInventorySheet.tsx`
- Modify: `frontend/src/app/(operator)/seller/inventory/bulk/page.tsx`

- [ ] **Step 1.1: Replace `BulkInventorySheet.tsx` contents**

Full new contents of `frontend/src/app/(operator)/seller/inventory/bulk/BulkInventorySheet.tsx`:

```tsx
"use client";

import type { SheetRow } from "./page";
import styles from "./bulk.module.css";

export type IndexedRow = { row: SheetRow; originalIndex: number };

interface Props {
  rows: IndexedRow[];
  selectedIndices: Set<number>;
  onToggleSelect: (idx: number) => void;
  onPatchRow: (idx: number, patch: Partial<SheetRow>) => void;
  onRemoveRow: (idx: number) => void;
}

export function BulkInventorySheet({
  rows,
  selectedIndices,
  onToggleSelect,
  onPatchRow,
  onRemoveRow,
}: Props) {
  if (rows.length === 0) return null;

  return (
    <div className={styles.sheetWrap}>
      <table className={styles.sheet}>
        <thead>
          <tr>
            <th></th>
            <th>Product</th>
            <th>Subcategory</th>
            <th>Price (₹)</th>
            <th>Stock</th>
            <th>Avl</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ row, originalIndex }) => {
            const isNew = row.inventory_id === null;
            const dirty = row.dirty;
            const rowClass = dirty
              ? isNew
                ? styles.rowNew
                : styles.rowDirty
              : "";
            return (
              <tr key={`${row.product_id}-${originalIndex}`} className={rowClass}>
                <td>
                  <input
                    type="checkbox"
                    checked={selectedIndices.has(originalIndex)}
                    onChange={() => onToggleSelect(originalIndex)}
                    aria-label={`Select ${row.product_name}`}
                  />
                </td>
                <td>{row.product_name}</td>
                <td>{row.subcategory_name}</td>
                <td>
                  <input
                    type="number"
                    className={
                      row.errors.price ? styles.cellErr : styles.cell
                    }
                    value={row.price}
                    min="0.01"
                    step="0.01"
                    onChange={(e) =>
                      onPatchRow(originalIndex, {
                        price: e.target.value,
                        dirty: true,
                        errors: validateCell(e.target.value, row.stock),
                      })
                    }
                  />
                  {row.errors.price && (
                    <div className={styles.cellErrMsg}>
                      {row.errors.price}
                    </div>
                  )}
                </td>
                <td>
                  <input
                    type="number"
                    className={
                      row.errors.stock ? styles.cellErr : styles.cell
                    }
                    value={row.stock}
                    min="0"
                    onChange={(e) =>
                      onPatchRow(originalIndex, {
                        stock: e.target.value,
                        dirty: true,
                        errors: validateCell(row.price, e.target.value),
                      })
                    }
                  />
                  {row.errors.stock && (
                    <div className={styles.cellErrMsg}>
                      {row.errors.stock}
                    </div>
                  )}
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={row.is_available}
                    onChange={(e) =>
                      onPatchRow(originalIndex, {
                        is_available: e.target.checked,
                        dirty: true,
                      })
                    }
                    aria-label={`Available ${row.product_name}`}
                  />
                </td>
                <td>
                  {isNew && (
                    <button
                      className="btn btn-outline"
                      onClick={() => onRemoveRow(originalIndex)}
                    >
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function validateCell(price: string, stock: string): SheetRow["errors"] {
  const errors: SheetRow["errors"] = {};
  const p = parseFloat(price);
  if (isNaN(p) || p <= 0 || p > 999999) {
    errors.price = "Price must be > 0 and ≤ 999999";
  }
  const s = parseInt(stock, 10);
  if (isNaN(s) || s < 0) {
    errors.stock = "Stock must be ≥ 0";
  }
  return errors;
}
```

Notes:
- New exported type `IndexedRow`.
- The header row now has 7 columns (was 8 — `Service` and `Category` merged into a single `Subcategory` column).
- Empty-state placeholder is removed; the page handles the empty case per category in Task 3. For a single-call use it's safe — `rows.length === 0 → return null`.

- [ ] **Step 1.2: Update `page.tsx` `BulkInventorySheet` invocation to pass `IndexedRow[]`**

In `frontend/src/app/(operator)/seller/inventory/bulk/page.tsx`, replace the existing `<BulkInventorySheet rows={rows} … />` block with:

```tsx
<BulkInventorySheet
  rows={rows.map((row, originalIndex) => ({ row, originalIndex }))}
  selectedIndices={selectedIndices}
  onToggleSelect={(idx) => {
    setSelectedIndices((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }}
  onPatchRow={(idx, patch) => {
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  }}
  onRemoveRow={(idx) => {
    setRows((prev) => prev.filter((_, i) => i !== idx));
    setSelectedIndices((prev) => {
      const next = new Set<number>();
      prev.forEach((i) => {
        if (i < idx) next.add(i);
        else if (i > idx) next.add(i - 1);
      });
      return next;
    });
  }}
/>
```

Note: also add a "no rows" placeholder shown when `rows.length === 0` (since the sheet now returns `null`):

Just above the `<BulkInventorySheet …>` block, add:

```tsx
{rows.length === 0 && (
  <div className={styles.empty}>
    No rows. Click &ldquo;Add products&rdquo; to start.
  </div>
)}
```

- [ ] **Step 1.3: Verify lint + build**

From `frontend/`:

```bash
npm run lint
npm run build
```

Expected: both clean.

- [ ] **Step 1.4: Manual verification**

Run `npm run dev`, log in as a seller, open `/seller/inventory/bulk`. Confirm:
- Sheet renders with the new 7-column layout (Product / Subcategory / Price / Stock / Avl / Remove).
- Checkbox / price / stock / available toggle / remove still work.
- Bulk-fill toolbar still operates on selected rows.
- Save still works.

- [ ] **Step 1.5: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/inventory/bulk/BulkInventorySheet.tsx frontend/src/app/\(operator\)/seller/inventory/bulk/page.tsx
git commit -m "refactor(seller): bulk sheet uses originalIndex and drops service/category columns"
```

---

## Task 2: Extend `EligibleProductPicker` with preset filters

Add optional `initialServiceId` / `initialCategoryId` props that seed the picker's filter dropdowns when it opens.

**Files:**
- Modify: `frontend/src/app/(operator)/seller/inventory/bulk/EligibleProductPicker.tsx`

- [ ] **Step 2.1: Update component signature + state init**

Replace the imports and `Props` type at the top of `frontend/src/app/(operator)/seller/inventory/bulk/EligibleProductPicker.tsx` with:

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import type { EligibleProduct } from "@/types";
import styles from "./bulk.module.css";

interface Props {
  open: boolean;
  products: EligibleProduct[];
  alreadyInSheet: Set<number>;
  onClose: () => void;
  onAdd: (selected: EligibleProduct[]) => void;
  initialServiceId?: number | null;
  initialCategoryId?: number | null;
}
```

In the component body, change the `useState` initialisations for `serviceId` / `categoryId` to seed from the props:

```tsx
export function EligibleProductPicker({
  open,
  products,
  alreadyInSheet,
  onClose,
  onAdd,
  initialServiceId = null,
  initialCategoryId = null,
}: Props) {
  const [search, setSearch] = useState("");
  const [serviceId, setServiceId] = useState<number | null>(initialServiceId);
  const [categoryId, setCategoryId] = useState<number | null>(initialCategoryId);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  // Re-apply preset whenever the picker is reopened with a new preset.
  useEffect(() => {
    if (open) {
      setServiceId(initialServiceId ?? null);
      setCategoryId(initialCategoryId ?? null);
      setSelected(new Set());
      setSearch("");
    }
  }, [open, initialServiceId, initialCategoryId]);
```

Leave the rest of the component unchanged.

- [ ] **Step 2.2: Verify lint + build**

```bash
npm run lint
npm run build
```

Expected: both clean (no callers pass the new props yet — they default to `null`).

- [ ] **Step 2.3: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/inventory/bulk/EligibleProductPicker.tsx
git commit -m "feat(seller): support preset filters in eligible product picker"
```

---

## Task 3: Bucket data by service & category, render tabs / nav / sections

The big rewrite of `page.tsx`. Adds: `?service=<slug>` URL state, fetch of categories, bucketing into `ServiceBucket[]`, service-tab strip, sticky category nav, per-category sections each rendering its own `BulkInventorySheet`, per-category `+ Add` opening the picker with a preset, "no services" / "no categories" notices.

**Files:**
- Modify: `frontend/src/app/(operator)/seller/inventory/bulk/page.tsx`
- Modify: `frontend/src/app/(operator)/seller/inventory/bulk/bulk.module.css`

- [ ] **Step 3.1: Add CSS classes for tabs / nav / sections / empty placeholders**

Append to `frontend/src/app/(operator)/seller/inventory/bulk/bulk.module.css`:

```css
.serviceTabs {
  display: flex;
  gap: var(--space-2);
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  -webkit-overflow-scrolling: touch;
  padding-bottom: var(--space-1);
}

.serviceTab {
  flex: 0 0 auto;
  scroll-snap-align: start;
  padding: var(--space-2) var(--space-4);
  font-size: var(--font-sm);
  font-weight: var(--weight-medium);
  color: var(--color-neutral-700);
  background: var(--color-neutral-100);
  border: 1px solid transparent;
  border-radius: var(--radius-full);
  cursor: pointer;
  white-space: nowrap;
  transition: all var(--duration-fast) var(--ease-default);
}

.serviceTab:hover {
  background: var(--color-neutral-200);
}

.serviceTabActive {
  background: var(--color-primary-50);
  color: var(--color-primary-700);
  border-color: var(--color-primary-200);
}

.serviceTabCount {
  margin-left: var(--space-2);
  font-size: var(--font-xs);
  color: var(--color-neutral-500);
  font-weight: var(--weight-regular);
}

.serviceTabActive .serviceTabCount {
  color: var(--color-primary-600);
}

.categoryNav {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  gap: var(--space-2);
  padding: var(--space-2) 0;
  background: var(--color-neutral-0);
  border-bottom: 1px solid var(--color-neutral-200);
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.categoryNavLink {
  flex: 0 0 auto;
  padding: var(--space-1) var(--space-3);
  font-size: var(--font-sm);
  color: var(--color-neutral-600);
  text-decoration: none;
  border-radius: var(--radius-md);
  white-space: nowrap;
  transition: background var(--duration-fast) var(--ease-default);
}

.categoryNavLink:hover {
  background: var(--color-neutral-100);
  color: var(--color-neutral-900);
}

.categoryNavCount {
  margin-left: var(--space-1);
  color: var(--color-neutral-500);
}

.categorySection {
  background: var(--color-neutral-0);
  border: 1px solid var(--color-neutral-200);
  border-radius: var(--radius-lg);
  overflow: hidden;
  scroll-margin-top: 56px;
}

.categoryHeader {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--color-neutral-50);
  border-bottom: 1px solid var(--color-neutral-200);
}

.categoryTitle {
  font-size: var(--font-base);
  font-weight: var(--weight-semibold);
  color: var(--color-neutral-900);
  margin: 0;
}

.categoryCount {
  margin-left: var(--space-2);
  font-size: var(--font-sm);
  color: var(--color-neutral-500);
  font-weight: var(--weight-regular);
}

.categoryAddBtn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-3);
  font-size: var(--font-sm);
  font-weight: var(--weight-medium);
  color: var(--color-primary-600);
  background: transparent;
  border: 1px solid var(--color-primary-200);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-default);
}

.categoryAddBtn:hover {
  background: var(--color-primary-50);
}

.emptyCategory {
  padding: var(--space-6);
  text-align: center;
  color: var(--color-neutral-500);
  font-size: var(--font-sm);
}

.servicesEmpty {
  padding: var(--space-6);
  text-align: center;
  color: var(--color-neutral-500);
  font-size: var(--font-sm);
}
```

- [ ] **Step 3.2: Replace `bulk/page.tsx` contents**

Full new contents of `frontend/src/app/(operator)/seller/inventory/bulk/page.tsx`:

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { get, put } from "@/lib/api";
import {
  BulkInventoryItem,
  Category,
  EligibleProduct,
  Service,
  Store,
  StoreInventory,
} from "@/types";

import styles from "./bulk.module.css";
import { BulkFillToolbar, type BulkFillAction } from "./BulkFillToolbar";
import { BulkInventorySheet, type IndexedRow } from "./BulkInventorySheet";
import { EligibleProductPicker } from "./EligibleProductPicker";

export type SheetRow = {
  inventory_id: number | null;
  product_id: number;
  product_name: string;
  service_id: number;
  service_name: string;
  category_id: number;
  category_name: string;
  subcategory_name: string;
  price: string;
  stock: string;
  is_available: boolean;
  dirty: boolean;
  errors: Partial<Record<"price" | "stock", string>>;
};

interface CategoryBucket {
  category: Category;
  rows: IndexedRow[];
}

interface ServiceBucket {
  service: Service;
  categories: CategoryBucket[];
  totalCount: number;
}

export default function BulkInventoryPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const activeServiceSlug = searchParams.get("service");
  const { dbUser, token, loading: authLoading } = useAuth();

  const [store, setStore] = useState<Store | null>(null);
  const [eligible, setEligible] = useState<EligibleProduct[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [rows, setRows] = useState<SheetRow[]>([]);
  const [fetching, setFetching] = useState(true);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerPreset, setPickerPreset] = useState<{
    serviceId: number;
    categoryId: number;
  } | null>(null);
  const [saving, setSaving] = useState(false);
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!authLoading && (!dbUser || dbUser.role !== "seller")) {
      router.push(dbUser ? "/" : "/login");
      return;
    }
    if (!authLoading && dbUser && token) {
      Promise.all([
        get<Store[]>("/api/v1/stores/my", token),
        get<EligibleProduct[]>("/api/v1/sellers/me/eligible-products", token),
        get<Category[]>("/api/v1/catalog/categories"),
      ])
        .then(async ([myStores, eligibleProducts, cats]) => {
          setEligible(eligibleProducts);
          setCategories(cats);
          if (myStores.length > 0) {
            const s = myStores[0];
            setStore(s);
            const inv = await get<StoreInventory[]>(
              `/api/v1/stores/${s.id}/inventory/all`,
              token,
            );
            const byProductId = new Map(
              eligibleProducts.map((p) => [p.id, p]),
            );
            setRows(
              inv
                .map((i) => {
                  const p = byProductId.get(i.product_id);
                  if (!p) return null;
                  const r: SheetRow = {
                    inventory_id: i.id,
                    product_id: p.id,
                    product_name: p.name,
                    service_id: p.service_id,
                    service_name: p.service_name,
                    category_id: p.category_id,
                    category_name: p.category_name,
                    subcategory_name: p.subcategory_name,
                    price: String(i.price),
                    stock: String(i.stock),
                    is_available: i.is_available,
                    dirty: false,
                    errors: {},
                  };
                  return r;
                })
                .filter((x): x is SheetRow => x !== null),
            );
          }
        })
        .catch(() => {})
        .finally(() => setFetching(false));
    }
  }, [authLoading, dbUser, token, router]);

  const alreadyInSheet = useMemo(
    () => new Set(rows.map((r) => r.product_id)),
    [rows],
  );

  const counts = useMemo(() => {
    let added = 0,
      edited = 0,
      invalid = 0;
    for (const r of rows) {
      const hasErr = Object.keys(r.errors).length > 0;
      if (hasErr) invalid++;
      if (r.dirty && !hasErr) {
        if (r.inventory_id === null) added++;
        else edited++;
      }
    }
    return { added, edited, invalid, total: rows.length };
  }, [rows]);

  const buckets: ServiceBucket[] = useMemo(() => {
    if (!store) return [];
    const catsByService = new Map<number, Category[]>();
    for (const c of categories) {
      const list = catsByService.get(c.service_id) ?? [];
      list.push(c);
      catsByService.set(c.service_id, list);
    }
    const indexed: IndexedRow[] = rows.map((row, originalIndex) => ({
      row,
      originalIndex,
    }));
    const rowsByCategory = new Map<number, IndexedRow[]>();
    for (const ir of indexed) {
      const list = rowsByCategory.get(ir.row.category_id) ?? [];
      list.push(ir);
      rowsByCategory.set(ir.row.category_id, list);
    }
    const services = [...store.services].sort(
      (a, b) => a.sort_order - b.sort_order,
    );
    return services.map((service) => {
      const serviceCats = (catsByService.get(service.id) ?? []).sort((a, b) =>
        a.name.localeCompare(b.name),
      );
      const categoryBuckets: CategoryBucket[] = serviceCats.map((category) => {
        const irs = (rowsByCategory.get(category.id) ?? []).slice().sort(
          (a, b) =>
            a.row.subcategory_name.localeCompare(b.row.subcategory_name) ||
            a.row.product_name.localeCompare(b.row.product_name),
        );
        return { category, rows: irs };
      });
      const totalCount = categoryBuckets.reduce((n, b) => n + b.rows.length, 0);
      return { service, categories: categoryBuckets, totalCount };
    });
  }, [store, categories, rows]);

  const activeBucket: ServiceBucket | null = useMemo(() => {
    if (buckets.length === 0) return null;
    if (activeServiceSlug) {
      const found = buckets.find((b) => b.service.slug === activeServiceSlug);
      if (found) return found;
    }
    return buckets[0];
  }, [buckets, activeServiceSlug]);

  function setActiveService(slug: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("service", slug);
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  }

  const canSave =
    !saving && counts.invalid === 0 && counts.added + counts.edited > 0;

  // Warn on tab close when there are unsaved rows.
  useEffect(() => {
    const hasDirty = rows.some((r) => r.dirty);
    if (!hasDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [rows]);

  async function handleSave() {
    if (!store || !token) return;
    setSaving(true);
    try {
      const items: BulkInventoryItem[] = rows
        .filter((r) => r.dirty && Object.keys(r.errors).length === 0)
        .map((r) => ({
          product_id: r.product_id,
          price: parseFloat(r.price),
          stock: parseInt(r.stock, 10),
          is_available: r.is_available,
        }));
      if (items.length === 0) {
        setSaving(false);
        return;
      }
      const updated = await put<StoreInventory[]>(
        `/api/v1/stores/${store.id}/inventory/bulk`,
        { items },
        token,
      );
      const byProduct = new Map(updated.map((u) => [u.product_id, u]));
      setRows((prev) =>
        prev.map((r) => {
          const u = byProduct.get(r.product_id);
          if (!u) return r;
          return {
            ...r,
            inventory_id: u.id,
            price: String(u.price),
            stock: String(u.stock),
            is_available: u.is_available,
            dirty: false,
            errors: {},
          };
        }),
      );
    } catch (err) {
      console.error("bulk save failed", err);
      alert("Save failed. Check rows for errors.");
    } finally {
      setSaving(false);
    }
  }

  function applyBulkFill(action: BulkFillAction) {
    setRows((prev) =>
      prev.map((row, idx) => {
        if (!selectedIndices.has(idx)) return row;
        const next: SheetRow = { ...row, dirty: true };
        if (action.kind === "set_price") {
          next.price = String(action.value);
        } else if (action.kind === "set_stock") {
          next.stock = String(action.value);
        } else {
          const current = parseFloat(row.price);
          if (!isNaN(current)) {
            const updated = current * (1 + action.pct / 100);
            next.price = updated.toFixed(2);
          }
        }
        const errors: SheetRow["errors"] = {};
        const p = parseFloat(next.price);
        if (isNaN(p) || p <= 0 || p > 999999)
          errors.price = "Price must be > 0 and ≤ 999999";
        const s = parseInt(next.stock, 10);
        if (isNaN(s) || s < 0) errors.stock = "Stock must be ≥ 0";
        next.errors = errors;
        return next;
      }),
    );
  }

  const onToggleSelect = (idx: number) => {
    setSelectedIndices((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const onPatchRow = (idx: number, patch: Partial<SheetRow>) => {
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  };

  const onRemoveRow = (idx: number) => {
    setRows((prev) => prev.filter((_, i) => i !== idx));
    setSelectedIndices((prev) => {
      const next = new Set<number>();
      prev.forEach((i) => {
        if (i < idx) next.add(i);
        else if (i > idx) next.add(i - 1);
      });
      return next;
    });
  };

  function openPickerForCategory(serviceId: number, categoryId: number) {
    setPickerPreset({ serviceId, categoryId });
    setPickerOpen(true);
  }

  function openPickerGlobal() {
    setPickerPreset(null);
    setPickerOpen(true);
  }

  if (authLoading || fetching) {
    return (
      <div style={{ padding: "2rem", textAlign: "center" }}>Loading…</div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.mobileBanner}>
        Bulk editor works best on a wider screen. Open from a desktop browser to use it comfortably.
      </div>
      <div className={styles.toolbar}>
        <Link href="/seller/inventory" className="btn btn-outline">
          ← Single edit
        </Link>
        <button
          className="btn btn-primary"
          onClick={openPickerGlobal}
          disabled={!store}
        >
          + Add products
        </button>
        <button
          className="btn btn-primary"
          onClick={handleSave}
          disabled={!canSave}
        >
          {saving ? "Saving…" : `Save ${counts.added + counts.edited} change(s)`}
        </button>
      </div>

      <div className={styles.statusBar}>
        {counts.added} new · {counts.edited} edited · {counts.invalid} invalid · {counts.total} total
      </div>

      <BulkFillToolbar
        selectedCount={selectedIndices.size}
        onApply={applyBulkFill}
      />

      {buckets.length > 0 && (
        <div className={styles.serviceTabs} role="tablist">
          {buckets.map(({ service, totalCount }) => {
            const isActive = service.id === activeBucket?.service.id;
            return (
              <button
                key={service.id}
                role="tab"
                aria-selected={isActive}
                className={`${styles.serviceTab} ${isActive ? styles.serviceTabActive : ""}`}
                onClick={() => setActiveService(service.slug)}
              >
                {service.name}
                <span className={styles.serviceTabCount}>({totalCount})</span>
              </button>
            );
          })}
        </div>
      )}

      {activeBucket && activeBucket.categories.length > 0 && (
        <nav className={styles.categoryNav} aria-label="Categories">
          {activeBucket.categories.map(({ category, rows: catRows }) => (
            <a
              key={category.id}
              href={`#cat-${category.id}`}
              className={styles.categoryNavLink}
            >
              {category.name}
              <span className={styles.categoryNavCount}>({catRows.length})</span>
            </a>
          ))}
        </nav>
      )}

      {buckets.length === 0 && (
        <div className={styles.servicesEmpty}>
          No services linked to this store. Contact admin.
        </div>
      )}

      {activeBucket && activeBucket.categories.length === 0 && (
        <div className={styles.servicesEmpty}>
          No categories in this service yet.
        </div>
      )}

      {activeBucket?.categories.map(({ category, rows: catRows }) => (
        <section
          key={category.id}
          id={`cat-${category.id}`}
          className={styles.categorySection}
        >
          <header className={styles.categoryHeader}>
            <h2 className={styles.categoryTitle}>
              {category.name}
              <span className={styles.categoryCount}>({catRows.length})</span>
            </h2>
            <button
              className={styles.categoryAddBtn}
              onClick={() =>
                openPickerForCategory(activeBucket.service.id, category.id)
              }
            >
              + Add
            </button>
          </header>
          {catRows.length === 0 ? (
            <div className={styles.emptyCategory}>
              No rows in this category yet.{" "}
              <button
                className={styles.categoryAddBtn}
                style={{ marginLeft: "var(--space-2)" }}
                onClick={() =>
                  openPickerForCategory(activeBucket.service.id, category.id)
                }
              >
                + Add
              </button>
            </div>
          ) : (
            <BulkInventorySheet
              rows={catRows}
              selectedIndices={selectedIndices}
              onToggleSelect={onToggleSelect}
              onPatchRow={onPatchRow}
              onRemoveRow={onRemoveRow}
            />
          )}
        </section>
      ))}

      <EligibleProductPicker
        open={pickerOpen}
        products={eligible}
        alreadyInSheet={alreadyInSheet}
        onClose={() => {
          setPickerOpen(false);
          setPickerPreset(null);
        }}
        initialServiceId={pickerPreset?.serviceId ?? null}
        initialCategoryId={pickerPreset?.categoryId ?? null}
        onAdd={(chosen) => {
          setRows((prev) => [
            ...prev,
            ...chosen.map<SheetRow>((p) => ({
              inventory_id: null,
              product_id: p.id,
              product_name: p.name,
              service_id: p.service_id,
              service_name: p.service_name,
              category_id: p.category_id,
              category_name: p.category_name,
              subcategory_name: p.subcategory_name,
              price: String(p.base_price),
              stock: "0",
              is_available: true,
              dirty: true,
              errors: {},
            })),
          ]);
          setPickerOpen(false);
          setPickerPreset(null);
        }}
      />
    </div>
  );
}
```

Notes:
- `SheetRow` gains `service_id` and `category_id` fields so bucketing works without a join. New rows added via the picker pass them in (the picker's `EligibleProduct` already exposes both).
- Active service selection mirrors the single-edit page implementation.
- `BulkInventorySheet` is now rendered once per category, each receiving the matching `IndexedRow[]`. Selection / patch / remove handlers live on the page and reference the original index — no per-section state.
- `openPickerForCategory(serviceId, categoryId)` sets `pickerPreset`; the picker reads it via `initialServiceId` / `initialCategoryId`.
- The bottom "no rows" placeholder from Task 1 step 1.2 is removed — the per-category empty state covers it now. (The `rows.length === 0 && …` block added in Task 1 step 1.2 should be removed; the new code does not include it.)

- [ ] **Step 3.3: Verify lint + build**

```bash
npm run lint
npm run build
```

Expected: both clean.

- [ ] **Step 3.4: Manual verification — desktop**

Run `npm run dev`, log in as a seller, open `/seller/inventory/bulk`. Confirm:
- Tabs render across the top, one per service. Active tab highlighted.
- Sticky category nav strip pins below the tabs while scrolling sections.
- Each category renders its own sheet.
- Edit price / stock / availability still work.
- Bulk-fill toolbar still applies to selected rows across services.
- Selecting rows in one tab and switching to another preserves selection.
- Save still saves all dirty rows.
- `+ Add products` (toolbar) opens picker with all filters cleared.
- `+ Add` per category opens picker with that service+category preset.
- `?service=<slug>` deep links work.

- [ ] **Step 3.5: Manual verification — edge cases**

- Seller with only one service in `store.services` → one tab.
- Service whose categories all have zero rows → still shows the section list, each section with empty placeholder + Add CTA.
- `?service=does-not-exist` → falls back to first tab.
- `rows.length === 0` (fresh seller) → tabs render with `(0)`, each category shows empty placeholder.

- [ ] **Step 3.6: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/inventory/bulk/page.tsx frontend/src/app/\(operator\)/seller/inventory/bulk/bulk.module.css
git commit -m "feat(seller): group bulk inventory editor by service & category"
```

---

## Task 4: Push branch and PR (PR awaits user approval)

- [ ] **Step 4.1: Push the branch**

```bash
git push -u origin feat/bulk-inventory-grouped
```

- [ ] **Step 4.2: Open PR (after explicit user approval per project rules)**

Per `CLAUDE.md`: wait for explicit user approval before opening the PR. Once approved:

```bash
gh pr create --title "feat(seller): group bulk inventory editor by service & category" --body "$(cat <<'EOF'
## Summary
- Bulk inventory editor now uses service tabs + sticky category nav + per-category sheets, mirroring the single-edit page.
- `BulkInventorySheet` refactored to take `Array<{row, originalIndex}>` so multiple instances can share the global selection / patch / remove handlers without index collisions.
- Drops Service / Category columns inside sheets. Subcategory column kept.
- Per-category `+ Add` opens the eligible-product picker pre-filtered to that category.

## Test plan
- [ ] Tabs render from `store.services`; counts match.
- [ ] `?service=<slug>` deep links work; unknown slug falls back to first tab.
- [ ] Sticky category nav jumps to the right section.
- [ ] Selection persists across tab switches; bulk-fill applies globally.
- [ ] Status bar + Save remain global.
- [ ] Per-category `+ Add` opens picker with service + category preset.
- [ ] Edit / remove / availability / save still work.
- [ ] Empty category shows placeholder with `+ Add` CTA.

Spec: `docs/superpowers/specs/2026-05-05-bulk-inventory-grouped-design.md`
EOF
)"
```

Do NOT pass `--delete-branch` on merge (project rule: keep merged branches).

---

## Self-Review Notes

- **Spec coverage:**
  - Service tabs / URL state — Task 3.
  - Sticky category nav — Task 3.
  - Per-category sheets, drop service/category columns, subcategory column — Tasks 1 + 3.
  - Global selection/save/dirty state — Task 3 (handlers live on page, sheets share via `originalIndex`).
  - Per-category `+ Add` with picker preset — Tasks 2 + 3.
  - `SheetRow` extended with `service_id` / `category_id` — Task 3 (was implicit in spec; required to bucket without joining via the eligible-product list).
  - Empty service / empty category notices — Task 3.
- **Placeholder scan:** all code blocks complete; no "TBD" / vague instructions.
- **Type consistency:** `IndexedRow = { row: SheetRow; originalIndex: number }` defined in Task 1, imported and reused in Task 3. Picker prop names `initialServiceId` / `initialCategoryId` consistent across Tasks 2 and 3. `pickerPreset` shape `{ serviceId, categoryId }` matches what `openPickerForCategory` writes.
- **`SheetRow` shape change:** Adding `service_id` / `category_id` is a breaking change to anyone importing `SheetRow`. Only `BulkInventorySheet` (which doesn't read these fields) and `page.tsx` itself use it. Safe.
- **Synthetic "Other" tab:** out of scope per single-edit decision; rows with category not in `store.services` are silently dropped from view (kept in `rows`).
