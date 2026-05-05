"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { get, put } from "@/lib/api";
import {
  BulkInventoryItem,
  EligibleProduct,
  Store,
  StoreInventory,
} from "@/types";

import styles from "./bulk.module.css";
import { BulkFillToolbar, type BulkFillAction } from "./BulkFillToolbar";
import { BulkInventorySheet } from "./BulkInventorySheet";
import { EligibleProductPicker } from "./EligibleProductPicker";

export type SheetRow = {
  inventory_id: number | null;
  product_id: number;
  product_name: string;
  service_name: string;
  category_name: string;
  subcategory_name: string;
  price: string;
  stock: string;
  is_available: boolean;
  dirty: boolean;
  errors: Partial<Record<"price" | "stock", string>>;
};

export default function BulkInventoryPage() {
  const router = useRouter();
  const { dbUser, token, loading: authLoading } = useAuth();

  const [store, setStore] = useState<Store | null>(null);
  const [eligible, setEligible] = useState<EligibleProduct[]>([]);
  const [rows, setRows] = useState<SheetRow[]>([]);
  const [fetching, setFetching] = useState(true);
  const [pickerOpen, setPickerOpen] = useState(false);
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
      ])
        .then(async ([myStores, eligibleProducts]) => {
          setEligible(eligibleProducts);
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
                    service_name: p.service_name,
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
          onClick={() => setPickerOpen(true)}
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

      {rows.length === 0 && (
        <div className={styles.empty}>
          No rows. Click &ldquo;Add products&rdquo; to start.
        </div>
      )}

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

      <EligibleProductPicker
        open={pickerOpen}
        products={eligible}
        alreadyInSheet={alreadyInSheet}
        onClose={() => setPickerOpen(false)}
        onAdd={(chosen) => {
          setRows((prev) => [
            ...prev,
            ...chosen.map<SheetRow>((p) => ({
              inventory_id: null,
              product_id: p.id,
              product_name: p.name,
              service_name: p.service_name,
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
        }}
      />
    </div>
  );
}
