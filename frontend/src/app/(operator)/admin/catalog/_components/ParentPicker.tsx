"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/AuthContext";
import { listCatalog } from "@/lib/catalog";
import type { CatalogEntity, EntityKind } from "@/types";
import styles from "./ParentPicker.module.css";

interface Props {
  parentEntity: EntityKind;
  value: number | null;
  onChange: (id: number) => void;
  /** Extra params to scope the search (e.g. category_id when picking a subcategory). */
  filterParams?: { service_id?: number; category_id?: number };
}

export function ParentPicker({
  parentEntity,
  value,
  onChange,
  filterParams = {},
}: Props) {
  const { token } = useAuth();
  const [q, setQ] = useState("");
  const [items, setItems] = useState<CatalogEntity[]>([]);
  const filterKey = JSON.stringify(filterParams);
  const reqIdRef = useRef(0);

  useEffect(() => {
    const reqId = ++reqIdRef.current;
    const t = setTimeout(() => {
      listCatalog(
        parentEntity,
        { q: q || undefined, is_active: true, page_size: 25, ...filterParams },
        token,
      )
        .then((res) => {
          if (reqIdRef.current !== reqId) return;
          setItems(res.items);
        })
        .catch(() => {
          if (reqIdRef.current !== reqId) return;
          setItems([]);
        });
    }, 200);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, parentEntity, filterKey, token]);

  return (
    <div className={styles.wrap}>
      <input
        type="text"
        placeholder="Search…"
        className={styles.search}
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <select
        className={styles.select}
        value={value ?? ""}
        onChange={(e) => onChange(Number(e.target.value))}
      >
        <option value="" disabled>
          Select parent…
        </option>
        {items.map((i) => (
          <option key={i.id} value={i.id}>
            {i.name} ({i.slug})
          </option>
        ))}
      </select>
    </div>
  );
}
