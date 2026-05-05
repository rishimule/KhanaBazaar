"use client";

import { useState } from "react";
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
      <span className={styles.bulkFillCount}>{selectedCount} selected</span>
      <button
        className="btn btn-outline"
        disabled={selectedCount === 0}
        onClick={() => setOpen(open === "price" ? null : "price")}
      >
        Set price…
      </button>
      <button
        className="btn btn-outline"
        disabled={selectedCount === 0}
        onClick={() => setOpen(open === "stock" ? null : "stock")}
      >
        Set stock…
      </button>
      <button
        className="btn btn-outline"
        disabled={selectedCount === 0}
        onClick={() => setOpen(open === "pct" ? null : "pct")}
      >
        Adjust price ±%…
      </button>

      {open !== null && (
        <div className={styles.bulkFillInline}>
          <input
            type="number"
            className={styles.cell}
            value={value}
            placeholder={
              open === "pct"
                ? "e.g. -10 for −10%"
                : open === "price"
                  ? "Price"
                  : "Stock"
            }
            onChange={(e) => setValue(e.target.value)}
          />
          <button
            className="btn btn-primary"
            onClick={() => submit(open)}
          >
            Apply
          </button>
        </div>
      )}
    </div>
  );
}
