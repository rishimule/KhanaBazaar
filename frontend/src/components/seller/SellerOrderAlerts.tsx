"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { useSellerOrderAlerts } from "@/lib/useSellerOrderAlerts";
import styles from "./SellerOrderAlerts.module.css";

const TOAST_MS = 15_000;

interface Props {
  /** Reports the pending-order count upward so the layout can badge the nav. */
  onPendingCountChange: (count: number | null) => void;
}

export default function SellerOrderAlerts({ onPendingCountChange }: Props) {
  const t = useTranslations("Seller.alerts");
  const router = useRouter();
  const {
    pendingCount,
    newOrderId,
    dismissNewOrder,
    soundEnabled,
    setSoundEnabled,
  } = useSellerOrderAlerts();

  useEffect(() => {
    onPendingCountChange(pendingCount);
  }, [pendingCount, onPendingCountChange]);

  // Auto-dismiss: the toast is pinned over the dashboard on every page, and
  // the nav badge + bell already carry the order persistently, so it does not
  // need to sit there until clicked.
  useEffect(() => {
    if (newOrderId === null) return;
    const timer = setTimeout(dismissNewOrder, TOAST_MS);
    return () => clearTimeout(timer);
  }, [newOrderId, dismissNewOrder]);

  return (
    <>
      <button
        type="button"
        className={styles.soundBtn}
        aria-pressed={soundEnabled}
        aria-label={soundEnabled ? t("disableSound") : t("enableSound")}
        title={soundEnabled ? t("soundOn") : t("soundOff")}
        onClick={() => setSoundEnabled(!soundEnabled)}
      >
        {soundEnabled ? "🔊" : "🔇"}
      </button>

      {newOrderId !== null && (
        <div className={styles.toast} role="alert">
          <div className={styles.toastText}>
            <strong>{t("newOrderTitle", { id: newOrderId })}</strong>
            <span>{t("newOrderBody")}</span>
          </div>
          <button
            type="button"
            className={styles.toastCta}
            onClick={() => {
              dismissNewOrder();
              router.push(`/seller/orders/${newOrderId}`);
            }}
          >
            {t("viewOrder")}
          </button>
          <button
            type="button"
            className={styles.toastClose}
            aria-label={t("dismiss")}
            onClick={dismissNewOrder}
          >
            ✕
          </button>
        </div>
      )}
    </>
  );
}
