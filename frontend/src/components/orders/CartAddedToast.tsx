"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { useCart } from "@/lib/CartContext";
import styles from "./CartAddedToast.module.css";

// Transient confirmation shown after a reorder fills the cart. Reads the
// count set by ReorderButton from CartContext, auto-dismisses after 4s, and
// clears the count on unmount so it is consumed exactly once.
export default function CartAddedToast() {
  const t = useTranslations("Reorder");
  const { lastReorderAdded, clearReorderAdded } = useCart();

  useEffect(() => {
    if (lastReorderAdded <= 0) return;
    const id = setTimeout(clearReorderAdded, 4000);
    return () => {
      clearTimeout(id);
      clearReorderAdded();
    };
  }, [lastReorderAdded, clearReorderAdded]);

  if (lastReorderAdded <= 0) return null;

  return (
    <div className={styles.toast} role="status" aria-live="polite">
      <span className={styles.check} aria-hidden="true">
        ✓
      </span>
      {t("addedToast", { count: lastReorderAdded })}
    </div>
  );
}
