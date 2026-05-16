"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import styles from "./SearchFilters.module.css";

const SORT_OPTIONS = [
  { value: "relevance", labelKey: "sortRelevance" as const },
  { value: "price_asc", labelKey: "sortPriceAsc" as const },
  { value: "price_desc", labelKey: "sortPriceDesc" as const },
  { value: "distance", labelKey: "sortDistance" as const },
];

export function SearchFilters() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const t = useTranslations("Search");

  function get(k: string): string {
    return sp.get(k) ?? "";
  }

  function update(k: string, v: string) {
    const params = new URLSearchParams(Array.from(sp.entries()));
    if (v) params.set(k, v);
    else params.delete(k);
    router.replace(`${pathname}?${params.toString()}`);
  }

  return (
    <div className={styles.bar}>
      <label className={styles.field}>
        <span className={styles.label}>{t("sort")}</span>
        <select
          value={get("sort") || "relevance"}
          onChange={(e) => update("sort", e.target.value)}
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {t(opt.labelKey)}
            </option>
          ))}
        </select>
      </label>
      <label className={styles.field}>
        <span className={styles.label}>{t("minPrice")}</span>
        <input
          type="number"
          inputMode="numeric"
          min={0}
          value={get("min_price")}
          onChange={(e) => update("min_price", e.target.value)}
        />
      </label>
      <label className={styles.field}>
        <span className={styles.label}>{t("maxPrice")}</span>
        <input
          type="number"
          inputMode="numeric"
          min={0}
          value={get("max_price")}
          onChange={(e) => update("max_price", e.target.value)}
        />
      </label>
    </div>
  );
}
