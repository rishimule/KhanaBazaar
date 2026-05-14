// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useTranslations } from "next-intl";
import { useCart } from "@/lib/CartContext";
import styles from "./ReplaceAdjustmentsBanner.module.css";

export default function ReplaceAdjustmentsBanner() {
  const t = useTranslations("Checkout.compare");
  const { lastReplaceAdjustments, clearReplaceAdjustments } = useCart();

  if (lastReplaceAdjustments.length === 0) return null;

  const counts = { stock_capped: 0, stock_exhausted: 0, item_unavailable: 0 };
  for (const a of lastReplaceAdjustments) counts[a.reason]++;

  const lines: string[] = [];
  if (counts.stock_capped > 0)
    lines.push(t("adjStockCapped", { count: counts.stock_capped }));
  if (counts.stock_exhausted > 0)
    lines.push(t("adjStockExhausted", { count: counts.stock_exhausted }));
  if (counts.item_unavailable > 0)
    lines.push(t("adjItemUnavailable", { count: counts.item_unavailable }));

  return (
    <div className={styles.banner} role="status">
      <strong>{t("bannerTitle")}</strong>
      <ul className={styles.list}>
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <button
        type="button"
        className={styles.dismiss}
        onClick={clearReplaceAdjustments}
        aria-label={t("bannerDismiss")}
      >
        ×
      </button>
    </div>
  );
}
