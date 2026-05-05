"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import {
  EligibleProduct,
  Store,
  StoreInventory,
} from "@/types";

import styles from "./bulk.module.css";
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

  if (authLoading || fetching) {
    return (
      <div style={{ padding: "2rem", textAlign: "center" }}>Loading…</div>
    );
  }

  return (
    <div className={styles.page}>
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
        <button className="btn btn-primary" disabled={true}>
          {saving ? "Saving…" : "Save"}
        </button>
      </div>

      <div className={styles.statusBar}>
        {rows.length} row(s) · {alreadyInSheet.size} unique products · {eligible.length} eligible
      </div>

      <BulkInventorySheet
        rows={rows}
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
