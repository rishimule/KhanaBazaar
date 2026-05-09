"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import { useCart } from "@/lib/CartContext";

export default function CartSyncBanner() {
  const t = useTranslations("Cart");
  const { lastSyncDropped, clearSyncDropped } = useCart();

  if (lastSyncDropped <= 0) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        background: "var(--color-warning-bg, #fff7e6)",
        color: "var(--color-warning-fg, #92400e)",
        borderBottom: "1px solid var(--color-warning-border, #fcd34d)",
        padding: "0.75rem 1rem",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: "1rem",
        fontSize: "0.9rem",
      }}
    >
      <span>{t("itemsDropped", { count: lastSyncDropped })}</span>
      <button
        type="button"
        onClick={clearSyncDropped}
        style={{
          background: "transparent",
          border: 0,
          cursor: "pointer",
          fontWeight: 600,
          color: "inherit",
        }}
      >
        {t("dismiss")}
      </button>
    </div>
  );
}
