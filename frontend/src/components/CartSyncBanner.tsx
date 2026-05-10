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
        background: "var(--mandarin-orange-light-1)",
        color: "var(--mandarin-orange-base-4)",
        borderBottom: "1px solid var(--hairline)",
        padding: "10px 16px",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: "12px",
        fontFamily: "var(--font-family-sans)",
        fontSize: "var(--body-sm)",
        fontWeight: 500,
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
