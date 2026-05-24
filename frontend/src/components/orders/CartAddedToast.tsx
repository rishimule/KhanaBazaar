"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { useCart } from "@/lib/CartContext";
import styles from "./CartAddedToast.module.css";

// Transient confirmation shown after a reorder fills the cart. ReorderButton
// sets the count on CartContext before navigating here; we render straight
// from that value and clear it via a timeout (auto-dismiss). The cleanup only
// cancels the timer — it does NOT clear the count — so the toast survives React
// StrictMode's mount→unmount→mount double-invoke in development.
export default function CartAddedToast() {
  const t = useTranslations("Reorder");
  const { lastReorderAdded, clearReorderAdded } = useCart();

  useEffect(() => {
    if (lastReorderAdded <= 0) return;
    const id = setTimeout(clearReorderAdded, 4000);
    return () => clearTimeout(id);
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
