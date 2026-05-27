"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useState } from "react";
import { useTranslations } from "next-intl";
import styles from "./bulk.module.css";

export type BulkFillAction =
  | { kind: "set_price"; value: number }
  | { kind: "set_stock"; value: number }
  | { kind: "adjust_price_pct"; pct: number };

interface Props {
  selectedCount: number;
  onApply: (action: BulkFillAction) => void;
}

export function BulkFillToolbar({ selectedCount, onApply }: Props) {
  const t = useTranslations("Seller.bulk");
  const [open, setOpen] = useState<null | "price" | "stock" | "pct">(null);
  const [value, setValue] = useState("");

  function submit(kind: "price" | "stock" | "pct") {
    const n = parseFloat(value);
    if (isNaN(n)) return;
    if (kind === "price") onApply({ kind: "set_price", value: n });
    else if (kind === "stock")
      onApply({ kind: "set_stock", value: Math.floor(n) });
    else onApply({ kind: "adjust_price_pct", pct: n });
    setValue("");
    setOpen(null);
  }

  return (
    <div className={styles.bulkFillWrap}>
      <span className={styles.bulkFillCount}>
        {t("selectedCount", { count: selectedCount })}
      </span>
      <button
        className="btn btn-outline"
        disabled={selectedCount === 0}
        onClick={() => setOpen(open === "price" ? null : "price")}
      >
        {t("setPrice")}
      </button>
      <button
        className="btn btn-outline"
        disabled={selectedCount === 0}
        onClick={() => setOpen(open === "stock" ? null : "stock")}
      >
        {t("setStock")}
      </button>
      <button
        className="btn btn-outline"
        disabled={selectedCount === 0}
        onClick={() => setOpen(open === "pct" ? null : "pct")}
      >
        {t("adjustPricePct")}
      </button>

      {open !== null && (
        <div className={styles.bulkFillInline}>
          <input
            type="number"
            className={styles.cell}
            value={value}
            placeholder={
              open === "pct"
                ? t("pctPlaceholder")
                : open === "price"
                  ? t("pricePlaceholder")
                  : t("stockPlaceholder")
            }
            onChange={(e) => setValue(e.target.value)}
          />
          <button
            className="btn btn-primary"
            onClick={() => submit(open)}
          >
            {t("apply")}
          </button>
        </div>
      )}
    </div>
  );
}
