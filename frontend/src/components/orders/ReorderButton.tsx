"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import { reorder } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import { useCart } from "@/lib/CartContext";
import styles from "./ReorderButton.module.css";

export default function ReorderButton({
  orderId,
  className,
}: {
  orderId: number;
  className?: string;
}) {
  const t = useTranslations("Reorder");
  const { token } = useAuth();
  const { addItem, setReplaceAdjustments } = useCart();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const handle = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!token || busy) return;
    setBusy(true);
    setMsg(null);
    try {
      const res = await reorder(token, orderId);
      for (const it of res.items) {
        await addItem(res.store_id, res.store_name, res.service_id, res.service_name, {
          product_id: it.product_id,
          inventory_id: it.inventory_id,
          product_name: it.product_name,
          quantity: it.quantity,
          price: it.unit_price,
          image_url: it.image_url ?? undefined,
        });
      }
      setReplaceAdjustments(res.adjustments);
      if (res.items.length === 0) {
        setMsg(t("nothingAvailable"));
      } else {
        router.push("/cart");
      }
    } catch (err) {
      const detail = (err as { detail?: string })?.detail;
      setMsg(detail === "service_unavailable" ? t("serviceUnavailable") : t("failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <span className={styles.wrap}>
      <button
        type="button"
        className={className ?? styles.btn}
        onClick={handle}
        disabled={busy}
      >
        {busy ? t("loading") : t("cta")} →
      </button>
      {msg && (
        <span className={styles.msg} role="status">
          {msg}
        </span>
      )}
    </span>
  );
}
