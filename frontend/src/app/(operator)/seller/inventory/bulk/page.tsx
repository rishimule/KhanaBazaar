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

      {pickerOpen && (
        <EligibleProductPicker
          key={`${pickerPreset?.serviceId ?? "all"}-${pickerPreset?.categoryId ?? "all"}`}
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
      )}
    </div>
  );
}
