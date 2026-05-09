"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useMemo, useState } from "react";
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

  const services = useMemo(() => {
    const map = new Map<number, string>();
    products.forEach((p) => map.set(p.service_id, p.service_name));
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [products]);

  const categories = useMemo(() => {
    const map = new Map<number, { name: string; service_id: number }>();
    products.forEach((p) =>
      map.set(p.category_id, {
        name: p.category_name,
        service_id: p.service_id,
      }),
    );
    return Array.from(map.entries()).map(([id, v]) => ({ id, ...v }));
  }, [products]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return products.filter((p) => {
      if (alreadyInSheet.has(p.id) || p.in_inventory) return false;
      if (serviceId !== null && p.service_id !== serviceId) return false;
      if (categoryId !== null && p.category_id !== categoryId) return false;
      if (q && !p.name.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [products, alreadyInSheet, search, serviceId, categoryId]);

  if (!open) return null;

  return (
    <div className={styles.pickerBackdrop} onClick={onClose}>
      <div
        className={styles.pickerPanel}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.pickerHeader}>
          <strong>Add products to sheet</strong>
          <button className="btn btn-outline" onClick={onClose}>
            ×
          </button>
        </div>
        <div className={styles.pickerFilters}>
          <input
            className={styles.cell}
            type="search"
            placeholder="Search products…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            value={serviceId ?? ""}
            onChange={(e) => {
              const v = e.target.value === "" ? null : Number(e.target.value);
              setServiceId(v);
              setCategoryId(null);
            }}
          >
            <option value="">All services</option>
            {services.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <select
            value={categoryId ?? ""}
            onChange={(e) =>
              setCategoryId(
                e.target.value === "" ? null : Number(e.target.value),
              )
            }
            disabled={serviceId === null}
          >
            <option value="">All categories</option>
            {categories
              .filter((c) => serviceId === null || c.service_id === serviceId)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
          </select>
        </div>

        <div className={styles.pickerList}>
          {services.length === 0 && (
            <div className={styles.empty}>
              You haven&apos;t been approved for any services yet. Contact admin.
            </div>
          )}
          {filtered.map((p) => (
            <label key={p.id} className={styles.pickerRow}>
              <input
                type="checkbox"
                checked={selected.has(p.id)}
                onChange={() => {
                  setSelected((prev) => {
                    const next = new Set(prev);
                    if (next.has(p.id)) next.delete(p.id);
                    else next.add(p.id);
                    return next;
                  });
                }}
              />
              <span className={styles.pickerName}>{p.name}</span>
              <span className={styles.pickerMeta}>
                {p.service_name} · {p.category_name} · ₹{p.base_price}
              </span>
            </label>
          ))}
        </div>

        <div className={styles.pickerFooter}>
          <button className="btn btn-outline" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            disabled={selected.size === 0}
            onClick={() => {
              const chosen = products.filter((p) => selected.has(p.id));
              onAdd(chosen);
              setSelected(new Set());
            }}
          >
            Add {selected.size} to sheet
          </button>
        </div>
      </div>
    </div>
  );
}
