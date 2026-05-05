# Seller Inventory — Grouped by Service & Category — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat seller inventory table with a service-tab + category-section layout: service tabs at top, sticky category-anchor strip, one DataTable per category with a Subcategory column.

**Architecture:** Single-page client component (`frontend/src/app/(operator)/seller/inventory/page.tsx`). Existing data fetches kept; `useMemo` builds a `byService → byCategory` bucket map. New small inline components (`InventoryServiceTabs`, `InventoryCategoryNav`, `InventoryCategorySection`) live in the same file. Existing `DataTable` and `Modal` components are reused as-is. Active service synced to URL via `?service=<slug>`.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript, CSS Modules. No new dependencies. Project has no frontend tests — verification is `npm run lint` + `npm run build` + manual browser verification.

**Spec:** `docs/superpowers/specs/2026-05-05-seller-inventory-grouped-design.md`

**Branch:** `feat/seller-inventory-grouped` (already created; spec already committed).

---

## Files Touched

- **Modify:** `frontend/src/app/(operator)/seller/inventory/page.tsx` — full rewrite of render tree; data-fetch and handlers preserved.
- **Modify:** `frontend/src/app/(operator)/seller/inventory/page.module.css` — add classes for service tabs, sticky nav strip, category section header, and empty-category placeholder.

No new files. No backend changes. No new dependencies.

---

## Task 1: Bucket data by service & category, render stacked category sections

Replace the single flat `DataTable` with one section per category of the seller's first service. Existing service tabs / nav strip not yet built — Task 2 and Task 3 add those. After this task the page already shows the new column set (Product / Subcategory / Price / Stock / Status / Actions) and groups visually.

**Files:**
- Modify: `frontend/src/app/(operator)/seller/inventory/page.tsx`
- Modify: `frontend/src/app/(operator)/seller/inventory/page.module.css`

- [ ] **Step 1.1: Add CSS classes for category section + empty placeholder**

Append to `frontend/src/app/(operator)/seller/inventory/page.module.css`:

```css
.categorySection {
  margin-bottom: var(--space-6);
  background: var(--color-neutral-0);
  border: 1px solid var(--color-neutral-200);
  border-radius: var(--radius-lg);
  overflow: hidden;
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

.categoryAddBtn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.emptyCategory {
  padding: var(--space-6);
  text-align: center;
  color: var(--color-neutral-500);
  font-size: var(--font-sm);
}
```

- [ ] **Step 1.2: Add subcategory ordering + bucketing logic to `page.tsx`**

In `frontend/src/app/(operator)/seller/inventory/page.tsx`, replace the `getCategoryName` helper and the `columns`/render block with the new bucketing + grouped render. Final structure of the file after this task:

```tsx
"use client";

import { useState, useMemo, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import DataTable, { Column } from "@/components/DataTable";
import Modal, { modalStyles } from "@/components/Modal";
import { useAuth } from "@/lib/AuthContext";
import { get, post, put, del } from "@/lib/api";
import {
  Store,
  StoreInventory,
  MasterProduct,
  Category,
  Service,
} from "@/types";

import styles from "./page.module.css";
import mobileStyles from "@/components/DataTableCard.module.css";

interface InventoryWithProduct extends StoreInventory {
  product: MasterProduct;
}

interface CategoryBucket {
  category: Category;
  items: InventoryWithProduct[];
}

interface ServiceBucket {
  service: Service;
  categories: CategoryBucket[];
  totalCount: number;
}

export default function SellerInventoryPage() {
  const router = useRouter();
  const { dbUser, token, loading: authLoading } = useAuth();

  const [store, setStore] = useState<Store | null>(null);
  const [inventory, setInventory] = useState<InventoryWithProduct[]>([]);
  const [allProducts, setAllProducts] = useState<MasterProduct[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [fetching, setFetching] = useState(true);

  const [editItem, setEditItem] = useState<InventoryWithProduct | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [formProductId, setFormProductId] = useState<number>(0);
  const [formPrice, setFormPrice] = useState("");
  const [formStock, setFormStock] = useState("");

  useEffect(() => {
    if (!authLoading && (!dbUser || dbUser.role !== "seller")) {
      router.push(dbUser ? "/" : "/login");
      return;
    }
    if (!authLoading && dbUser && token) {
      Promise.all([
        get<Store[]>("/api/v1/stores/my", token),
        get<MasterProduct[]>("/api/v1/catalog/products"),
        get<Category[]>("/api/v1/catalog/categories"),
      ])
        .then(async ([myStores, products, cats]) => {
          setAllProducts(products);
          setCategories(cats);
          if (myStores.length > 0) {
            const s = myStores[0];
            setStore(s);
            const inv = await get<StoreInventory[]>(
              `/api/v1/stores/${s.id}/inventory/all`,
              token
            );
            const productMap = new Map(products.map((p) => [p.id, p]));
            setInventory(
              inv
                .map((i) => ({ ...i, product: productMap.get(i.product_id)! }))
                .filter((i) => i.product)
            );
          }
        })
        .catch(() => {})
        .finally(() => setFetching(false));
    }
  }, [authLoading, dbUser, token, router]);

  const buckets: ServiceBucket[] = useMemo(() => {
    if (!store) return [];
    const catsByService = new Map<number, Category[]>();
    for (const c of categories) {
      const list = catsByService.get(c.service_id) ?? [];
      list.push(c);
      catsByService.set(c.service_id, list);
    }
    const itemsByCategory = new Map<number, InventoryWithProduct[]>();
    for (const item of inventory) {
      const list = itemsByCategory.get(item.product.category_id) ?? [];
      list.push(item);
      itemsByCategory.set(item.product.category_id, list);
    }
    const services = [...store.services].sort(
      (a, b) => a.sort_order - b.sort_order
    );
    return services.map((service) => {
      const serviceCats = (catsByService.get(service.id) ?? []).sort((a, b) =>
        a.name.localeCompare(b.name)
      );
      const categoryBuckets: CategoryBucket[] = serviceCats.map((category) => {
        const items = (itemsByCategory.get(category.id) ?? []).sort(
          (a, b) =>
            a.product.subcategory_name.localeCompare(b.product.subcategory_name) ||
            a.product.name.localeCompare(b.product.name)
        );
        return { category, items };
      });
      const totalCount = categoryBuckets.reduce((n, b) => n + b.items.length, 0);
      return { service, categories: categoryBuckets, totalCount };
    });
  }, [store, categories, inventory]);

  const activeBucket: ServiceBucket | null = buckets[0] ?? null;

  const availableProducts = useMemo(() => {
    const existingIds = new Set(inventory.map((i) => i.product_id));
    return allProducts.filter((p) => !existingIds.has(p.id));
  }, [inventory, allProducts]);

  const columns: Column<InventoryWithProduct>[] = [
    {
      key: "product_name",
      label: "Product",
      render: (row) => <strong>{row.product.name}</strong>,
    },
    {
      key: "subcategory",
      label: "Subcategory",
      render: (row) => row.product.subcategory_name,
    },
    { key: "price", label: "Price (₹)", render: (row) => `₹${row.price}` },
    { key: "stock", label: "Stock", render: (row) => String(row.stock) },
    {
      key: "is_available",
      label: "Status",
      render: (row) => (
        <button
          className={`${styles.toggleBtn} ${
            row.is_available ? styles.toggleActive : styles.toggleInactive
          }`}
          onClick={() => toggleAvailability(row)}
        >
          {row.is_available ? "Available" : "Unavailable"}
        </button>
      ),
    },
  ];

  async function toggleAvailability(item: InventoryWithProduct) {
    if (!store || !token) return;
    try {
      await put(
        `/api/v1/stores/${store.id}/inventory/${item.id}`,
        { is_available: !item.is_available, price: item.price, stock: item.stock },
        token
      );
      setInventory((prev) =>
        prev.map((i) =>
          i.id === item.id ? { ...i, is_available: !i.is_available } : i
        )
      );
    } catch { /* silent */ }
  }

  function handleEdit(item: InventoryWithProduct) {
    setEditItem(item);
    setFormPrice(String(item.price));
    setFormStock(String(item.stock));
  }

  async function handleSaveEdit() {
    if (!editItem || !store || !token) return;
    try {
      await put(
        `/api/v1/stores/${store.id}/inventory/${editItem.id}`,
        {
          price: parseFloat(formPrice) || editItem.price,
          stock: parseInt(formStock, 10) ?? editItem.stock,
          is_available: editItem.is_available,
        },
        token
      );
      setInventory((prev) =>
        prev.map((i) =>
          i.id === editItem.id
            ? {
                ...i,
                price: parseFloat(formPrice) || i.price,
                stock: parseInt(formStock, 10) ?? i.stock,
              }
            : i
        )
      );
      setEditItem(null);
    } catch { /* silent */ }
  }

  async function handleDelete(item: InventoryWithProduct) {
    if (!store || !token) return;
    try {
      await del(`/api/v1/stores/${store.id}/inventory/${item.id}`, token);
      setInventory((prev) => prev.filter((i) => i.id !== item.id));
    } catch { /* silent */ }
  }

  function openAdd() {
    setFormProductId(availableProducts[0]?.id ?? 0);
    setFormPrice("");
    setFormStock("");
    setShowAdd(true);
  }

  async function handleAdd() {
    if (!store || !token) return;
    const product = allProducts.find((p) => p.id === formProductId);
    if (!product) return;
    try {
      const created = await post<StoreInventory>(
        `/api/v1/stores/${store.id}/inventory`,
        {
          product_id: product.id,
          price: parseFloat(formPrice) || product.base_price,
          stock: parseInt(formStock, 10) || 0,
          is_available: true,
        },
        token
      );
      setInventory((prev) => [...prev, { ...created, product }]);
      setShowAdd(false);
    } catch { /* silent */ }
  }

  if (authLoading || fetching) {
    return (
      <div style={{ padding: "2rem", textAlign: "center", color: "var(--color-neutral-500)" }}>
        Loading…
      </div>
    );
  }

  return (
    <>
      <div className={styles.toolbar}>
        <span className={styles.toolbarLeft}>
          {inventory.length} products in store
        </span>
        <Link href="/seller/inventory/bulk" className="btn btn-outline">
          Bulk edit →
        </Link>
        <button
          className={styles.addBtn}
          onClick={openAdd}
          disabled={availableProducts.length === 0}
        >
          + Add Product
        </button>
      </div>

      {activeBucket?.categories.map((bucket) => (
        <section
          key={bucket.category.id}
          id={`cat-${bucket.category.id}`}
          className={styles.categorySection}
        >
          <header className={styles.categoryHeader}>
            <h2 className={styles.categoryTitle}>
              {bucket.category.name}
              <span className={styles.categoryCount}>({bucket.items.length})</span>
            </h2>
          </header>
          {bucket.items.length === 0 ? (
            <div className={styles.emptyCategory}>
              No products in this category yet.
            </div>
          ) : (
            <DataTable
              columns={columns}
              data={bucket.items}
              keyField="id"
              onEdit={handleEdit}
              onDelete={handleDelete}
              mobileCardRender={(row) => (
                <>
                  <div className={mobileStyles.cardTopRow}>
                    <span className={mobileStyles.cardTitle}>{row.product.name}</span>
                    <span className={mobileStyles.cardPriceRight}>₹{row.price}</span>
                  </div>
                  <div className={mobileStyles.cardMeta}>
                    {row.product.subcategory_name} • Stock: {row.stock}
                  </div>
                  <button
                    className={`${styles.toggleBtn} ${
                      row.is_available ? styles.toggleActive : styles.toggleInactive
                    }`}
                    style={{ width: "100%", minHeight: 44 }}
                    onClick={() => toggleAvailability(row)}
                  >
                    {row.is_available ? "Available" : "Unavailable"}
                  </button>
                </>
              )}
            />
          )}
        </section>
      ))}

      {editItem && (
        <Modal
          title={`Edit — ${editItem.product.name}`}
          onClose={() => setEditItem(null)}
          footer={
            <>
              <button className="btn btn-outline" onClick={() => setEditItem(null)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleSaveEdit}>Save Changes</button>
            </>
          }
        >
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Price (₹)</label>
            <input
              type="number"
              className={modalStyles.input}
              value={formPrice}
              onChange={(e) => setFormPrice(e.target.value)}
              min="0"
              step="0.01"
            />
          </div>
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Stock</label>
            <input
              type="number"
              className={modalStyles.input}
              value={formStock}
              onChange={(e) => setFormStock(e.target.value)}
              min="0"
            />
          </div>
        </Modal>
      )}

      {showAdd && (
        <Modal
          title="Add Product to Store"
          onClose={() => setShowAdd(false)}
          footer={
            <>
              <button className="btn btn-outline" onClick={() => setShowAdd(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleAdd}>Add Product</button>
            </>
          }
        >
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Product</label>
            <select
              className={modalStyles.select}
              value={formProductId}
              onChange={(e) => setFormProductId(parseInt(e.target.value, 10))}
            >
              {availableProducts.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} — ₹{p.base_price}
                </option>
              ))}
            </select>
          </div>
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Your Price (₹)</label>
            <input
              type="number"
              className={modalStyles.input}
              value={formPrice}
              onChange={(e) => setFormPrice(e.target.value)}
              placeholder="Leave blank to use base price"
              min="0"
              step="0.01"
            />
          </div>
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Stock Quantity</label>
            <input
              type="number"
              className={modalStyles.input}
              value={formStock}
              onChange={(e) => setFormStock(e.target.value)}
              placeholder="0"
              min="0"
            />
          </div>
        </Modal>
      )}
    </>
  );
}
```

Notes:
- The `Service` import is added; it is used for the bucket type.
- `categories` and `allProducts` array states are reused — no new fetches.
- `activeBucket` is currently the first `ServiceBucket`; the URL-driven selection comes in Task 2.
- Empty categories render the `emptyCategory` div instead of letting `DataTable` show its built-in empty state — this keeps the look consistent and avoids the `📋` icon for every empty category.

- [ ] **Step 1.3: Verify lint + types**

Run from `frontend/`:

```bash
npm run lint
```

Expected: no errors, no warnings.

```bash
npm run build
```

Expected: build completes; `/seller/inventory` route compiles.

- [ ] **Step 1.4: Manual verification in dev**

From `frontend/`:

```bash
npm run dev
```

Open `http://localhost:3000/seller/inventory` as a logged-in seller. Confirm:
- Categories render as separate sections with the new column set (Product | Subcategory | Price | Stock | Status | Actions).
- Subcategory column shows non-empty values for existing rows.
- Edit / Delete / availability toggle still work.
- Add Product modal still works (global button only at this stage).

- [ ] **Step 1.5: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/inventory/page.tsx frontend/src/app/\(operator\)/seller/inventory/page.module.css
git commit -m "feat(seller): group inventory by category with subcategory column"
```

---

## Task 2: Service tabs with `?service=<slug>` URL state

Add a tab strip above the category sections. Tabs are derived from `store.services` (sorted by `sort_order`). Active service is read from / written to `?service=<slug>`. Default = first service.

**Files:**
- Modify: `frontend/src/app/(operator)/seller/inventory/page.tsx`
- Modify: `frontend/src/app/(operator)/seller/inventory/page.module.css`

- [ ] **Step 2.1: Add CSS classes for service tabs**

Append to `frontend/src/app/(operator)/seller/inventory/page.module.css`:

```css
.serviceTabs {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
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

.servicesEmpty {
  padding: var(--space-6);
  text-align: center;
  color: var(--color-neutral-500);
  font-size: var(--font-sm);
}
```

- [ ] **Step 2.2: Opt out of static generation**

Add at the top of `frontend/src/app/(operator)/seller/inventory/page.tsx`, just after the `"use client";` directive (still above all imports):

```tsx
"use client";

export const dynamic = "force-dynamic";
```

This is required because `useSearchParams` (added in this task) errors at build time without either a `<Suspense>` wrapper or a dynamic opt-in. The page is already auth-gated, so static generation provides no value.

- [ ] **Step 2.3: Wire `useSearchParams` + render tabs**

In `frontend/src/app/(operator)/seller/inventory/page.tsx`:

1. Update the `next/navigation` import:

```tsx
import { useRouter, useSearchParams, usePathname } from "next/navigation";
```

2. After `const router = useRouter();` add:

```tsx
const pathname = usePathname();
const searchParams = useSearchParams();
const activeServiceSlug = searchParams.get("service");
```

3. Replace `const activeBucket: ServiceBucket | null = buckets[0] ?? null;` with:

```tsx
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
```

4. Add the inline `InventoryServiceTabs` component above `export default`:

```tsx
function InventoryServiceTabs({
  buckets,
  activeId,
  onChange,
}: {
  buckets: ServiceBucket[];
  activeId: number | null;
  onChange: (slug: string) => void;
}) {
  if (buckets.length === 0) return null;
  return (
    <div className={styles.serviceTabs} role="tablist">
      {buckets.map(({ service, totalCount }) => {
        const isActive = service.id === activeId;
        return (
          <button
            key={service.id}
            role="tab"
            aria-selected={isActive}
            className={`${styles.serviceTab} ${isActive ? styles.serviceTabActive : ""}`}
            onClick={() => onChange(service.slug)}
          >
            {service.name}
            <span className={styles.serviceTabCount}>({totalCount})</span>
          </button>
        );
      })}
    </div>
  );
}
```

5. Render the tab strip just below the toolbar in the JSX. Replace the JSX block that currently starts with `{activeBucket?.categories.map(...)` so it now begins with the tabs and a no-services fallback:

```tsx
<InventoryServiceTabs
  buckets={buckets}
  activeId={activeBucket?.service.id ?? null}
  onChange={setActiveService}
/>

{buckets.length === 0 && (
  <div className={styles.servicesEmpty}>
    No services linked to this store. Contact admin.
  </div>
)}

{activeBucket?.categories.map((bucket) => (
  // ...existing category section JSX unchanged...
))}
```

- [ ] **Step 2.4: Verify lint + build**

```bash
npm run lint
npm run build
```

Expected: both clean.

- [ ] **Step 2.5: Manual verification**

In `npm run dev`:
- Tab strip appears with one tab per service in `store.services`.
- Active tab highlighted.
- Click on another tab → URL changes to `?service=<slug>` and category sections swap.
- Direct nav to `/seller/inventory?service=grocery` lands on the matching tab.
- Direct nav with an unknown slug falls back to first tab.

- [ ] **Step 2.6: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/inventory/page.tsx frontend/src/app/\(operator\)/seller/inventory/page.module.css
git commit -m "feat(seller): add service tabs to inventory page"
```

---

## Task 3: Sticky category nav strip

Render an anchor strip below the service tabs with one link per category in the active service. Sticky to the viewport top. Click scrolls the matching `<section id="cat-<id>">` into view.

**Files:**
- Modify: `frontend/src/app/(operator)/seller/inventory/page.tsx`
- Modify: `frontend/src/app/(operator)/seller/inventory/page.module.css`

- [ ] **Step 3.1: Add CSS classes for the nav strip**

Append to `frontend/src/app/(operator)/seller/inventory/page.module.css`:

```css
.categoryNav {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  gap: var(--space-2);
  padding: var(--space-2) 0;
  margin-bottom: var(--space-4);
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
```

Also extend `.categorySection` to add `scroll-margin-top` so the sticky strip doesn't cover the section header on jump:

```css
.categorySection {
  scroll-margin-top: 56px;
}
```

(Update the existing `.categorySection` rule from Task 1; merge `scroll-margin-top: 56px;` into it rather than duplicating.)

- [ ] **Step 3.2: Add `InventoryCategoryNav` component**

In `frontend/src/app/(operator)/seller/inventory/page.tsx`, just below `InventoryServiceTabs`:

```tsx
function InventoryCategoryNav({ categories }: { categories: CategoryBucket[] }) {
  if (categories.length === 0) return null;
  return (
    <nav className={styles.categoryNav} aria-label="Categories">
      {categories.map(({ category, items }) => (
        <a
          key={category.id}
          href={`#cat-${category.id}`}
          className={styles.categoryNavLink}
        >
          {category.name}
          <span className={styles.categoryNavCount}>({items.length})</span>
        </a>
      ))}
    </nav>
  );
}
```

- [ ] **Step 3.3: Render the nav strip**

In the page JSX, render `InventoryCategoryNav` between the service tabs and the category sections:

```tsx
<InventoryServiceTabs
  buckets={buckets}
  activeId={activeBucket?.service.id ?? null}
  onChange={setActiveService}
/>

{activeBucket && (
  <InventoryCategoryNav categories={activeBucket.categories} />
)}

{/* ...existing no-services fallback + category section map... */}
```

- [ ] **Step 3.4: Verify lint + build**

```bash
npm run lint
npm run build
```

Expected: both clean.

- [ ] **Step 3.5: Manual verification**

In `npm run dev`:
- Strip renders below tabs with one link per category in active service.
- Strip stays pinned to top while scrolling category sections.
- Clicking a strip link scrolls the matching section into view.
- Counts in the strip match counts in the category headers.

- [ ] **Step 3.6: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/inventory/page.tsx frontend/src/app/\(operator\)/seller/inventory/page.module.css
git commit -m "feat(seller): add sticky category nav strip on inventory page"
```

---

## Task 4: Per-category "+ Add" button with preset category filter

Add a small `+ Add` button to each category-section header. Clicking opens the existing Add modal with the product dropdown pre-filtered to products in that category. The global `+ Add Product` button (in the toolbar) keeps its existing behaviour (no preset).

**Files:**
- Modify: `frontend/src/app/(operator)/seller/inventory/page.tsx`

(No CSS additions — `categoryAddBtn` was added in Task 1.)

- [ ] **Step 4.1: Add preset state + open helper**

Just below the existing `formStock` state declaration in `page.tsx`, add:

```tsx
const [presetCategoryId, setPresetCategoryId] = useState<number | null>(null);
```

Replace the existing `openAdd` function with:

```tsx
function openAdd(categoryId?: number) {
  const pool = categoryId
    ? availableProducts.filter((p) => p.category_id === categoryId)
    : availableProducts;
  setPresetCategoryId(categoryId ?? null);
  setFormProductId(pool[0]?.id ?? 0);
  setFormPrice("");
  setFormStock("");
  setShowAdd(true);
}
```

Update the modal-close handler (in the `Add Modal` JSX) so cancelling clears the preset:

```tsx
onClose={() => { setShowAdd(false); setPresetCategoryId(null); }}
```

And the cancel button:

```tsx
<button
  className="btn btn-outline"
  onClick={() => { setShowAdd(false); setPresetCategoryId(null); }}
>
  Cancel
</button>
```

In `handleAdd`, after `setShowAdd(false);` add `setPresetCategoryId(null);`:

```tsx
setShowAdd(false);
setPresetCategoryId(null);
```

- [ ] **Step 4.2: Use preset to filter the modal product list**

Inside the Add modal JSX, replace the `<select>` body so it iterates over a filtered list:

```tsx
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
```

- [ ] **Step 4.3: Render the per-category Add button**

Inside the `categoryHeader` for each `categorySection`, after the `<h2>`, add:

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

Final category-header markup:

```tsx
<header className={styles.categoryHeader}>
  <h2 className={styles.categoryTitle}>
    {bucket.category.name}
    <span className={styles.categoryCount}>({bucket.items.length})</span>
  </h2>
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
</header>
```

Also update the empty-category placeholder so seller has a CTA there too:

```tsx
{bucket.items.length === 0 ? (
  <div className={styles.emptyCategory}>
    No products in this category yet.{" "}
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
  </div>
) : (
  <DataTable ... />
)}
```

- [ ] **Step 4.4: Verify lint + build**

```bash
npm run lint
npm run build
```

Expected: both clean.

- [ ] **Step 4.5: Manual verification**

In `npm run dev`:
- Each category header shows a `+ Add` button.
- Clicking it opens the Add modal with only that category's available products in the dropdown.
- Submitting adds a row to the correct category.
- Cancel + reopening the global toolbar `+ Add Product` shows the full unfiltered product list (preset cleared).
- A category whose every master product is already in inventory shows a disabled `+ Add`.

- [ ] **Step 4.6: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/inventory/page.tsx
git commit -m "feat(seller): per-category add product with preset filter"
```

---

## Task 5: Mobile responsive polish + edge-case verification

Final pass: confirm mobile layout, defensive handling, and overall styling.

**Files:**
- Modify: `frontend/src/app/(operator)/seller/inventory/page.module.css`

- [ ] **Step 5.1: Tighten mobile spacing**

Append (or merge) to `frontend/src/app/(operator)/seller/inventory/page.module.css`:

```css
@media (max-width: 480px) {
  .serviceTabs {
    margin-left: calc(-1 * var(--space-3));
    margin-right: calc(-1 * var(--space-3));
    padding-left: var(--space-3);
    padding-right: var(--space-3);
  }

  .categoryNav {
    margin-left: calc(-1 * var(--space-3));
    margin-right: calc(-1 * var(--space-3));
    padding-left: var(--space-3);
    padding-right: var(--space-3);
  }

  .categoryHeader {
    flex-wrap: wrap;
  }

  .categorySection {
    scroll-margin-top: 64px;
  }
}
```

- [ ] **Step 5.2: Verify lint + build**

```bash
npm run lint
npm run build
```

Expected: both clean.

- [ ] **Step 5.3: Manual verification — desktop + mobile + edge cases**

In `npm run dev`, in a browser with devtools:

Desktop (≥768px):
- Service tabs render in a row.
- Sticky category strip pins to top while scrolling.
- Category sections each show a table with the new column set.
- Edit / Delete / availability toggle still work.
- Per-category `+ Add` and global `+ Add Product` both work.
- Bulk edit link still navigates to `/seller/inventory/bulk`.

Mobile (≤480px, e.g. iPhone SE viewport):
- Service tabs scroll horizontally with snap.
- Category strip scrolls horizontally.
- Tables fall back to card layout; card meta shows `<subcategory> • Stock: <n>`.
- Toolbar stacks; `+ Add Product` is full-width.

Edge cases:
- Test a seller whose store has only one service → tab strip still renders one tab.
- Test a category with no inventory rows → empty placeholder + `+ Add` CTA shows.
- Test direct nav to `/seller/inventory?service=does-not-exist` → falls back to first service.

- [ ] **Step 5.4: Commit**

```bash
git add frontend/src/app/\(operator\)/seller/inventory/page.module.css
git commit -m "chore(seller): mobile polish for grouped inventory page"
```

---

## Task 6: Push branch and open PR

- [ ] **Step 6.1: Push the branch**

```bash
git push -u origin feat/seller-inventory-grouped
```

- [ ] **Step 6.2: Open PR (after explicit user approval per project rules)**

Per `CLAUDE.md`: wait for explicit user approval before opening the PR. Once approved:

```bash
gh pr create --title "feat(seller): group inventory by service & category" --body "$(cat <<'EOF'
## Summary
- Replaces the flat seller inventory table with service tabs + sticky category nav + per-category tables.
- Adds a Subcategory column inside each category table.
- Per-category and global "+ Add" flows, with the per-category modal pre-filtered to that category.

## Test plan
- [ ] Verify service tabs render from `store.services` and `?service=<slug>` deep-links work.
- [ ] Verify category nav strip jumps to the correct section.
- [ ] Verify edit / delete / availability toggle still work.
- [ ] Verify per-category + Add filters product list correctly.
- [ ] Verify mobile (≤480px) tabs and nav strip scroll horizontally and tables collapse to cards.
- [ ] Verify empty categories show placeholder with `+ Add` CTA.

Spec: `docs/superpowers/specs/2026-05-05-seller-inventory-grouped-design.md`
EOF
)"
```

Do NOT pass `--delete-branch` on merge (project rule: keep merged branches).

---

## Self-Review Notes

- Spec coverage: every spec section is covered — service tabs (Task 2), category nav (Task 3), category sections + subcategory column (Task 1), empty placeholders (Task 1 + Task 4), URL state (Task 2), per-category Add with preset (Task 4), mobile (Task 5), defensive no-services notice (Task 2 step 2.2 step 5).
- Synthetic "Other" tab from spec edge cases is intentionally **not implemented**: in the bucketing pass, an inventory row whose product's category is missing from the active store's services is silently dropped. This matches the documented backend invariant that a seller can only stock products under their store's services. If a bug ever produces orphan rows, they will fail to surface on this page — acceptable for MVP. Document this as a follow-up only if a real case is observed.
- All code blocks contain final code, no placeholders.
- File paths are exact; CSS additions are appended, not duplicated.
