"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useState } from "react";
import { useTranslations } from "next-intl";
import { resendDeliveryOtp } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import { ApiError } from "@/lib/api";
import type { Order } from "@/types";
import styles from "./DeliveryOtpPanel.module.css";

interface Props {
  order: Order;
  onChange: (next: Order) => void;
  /**
   * i18n namespace holding the panel copy. Defaults to the customer namespace;
   * the admin order page passes "Admin.orderDetail" for admin-voiced copy.
   */
  namespace?: string;
}

/**
 * Handover code panel, shown only while the order is dispatched and the backend
 * exposes the code (owning customer or admin). Includes a cooldown-aware resend
 * button. Sellers never receive the code, so this renders nothing for them.
 */
export default function DeliveryOtpPanel({
  order,
  onChange,
  namespace = "Account.orderDetail",
}: Props) {
  const t = useTranslations(namespace);
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const code = order.delivery.otp;
  if (order.status !== "dispatched" || !code) return null;

  const handleResend = async () => {
    if (!token) return;
    setBusy(true);
    setNote(null);
    try {
      const next = await resendDeliveryOtp(token, order.id);
      onChange(next);
      setNote(t("resendDone"));
    } catch (e) {
      if (
        e instanceof ApiError &&
        e.detail &&
        typeof e.detail === "object" &&
        (e.detail as { code?: string }).code === "resend_cooldown"
      ) {
        const retry = (e.detail as { retry_after?: number }).retry_after ?? 0;
        setNote(t("resendCooldown", { seconds: retry }));
      } else {
        setNote(t("resendError"));
      }
    } finally {
      setBusy(false);
    }
  };

  const isPickup = order.delivery_mode === "pickup";
  return (
    <section className={styles.panel}>
      <h2 className={styles.title}>
        {t(isPickup ? "deliveryCodeTitlePickup" : "deliveryCodeTitle")}
      </h2>
      <p className={styles.code}>{code}</p>
      <p className={styles.hint}>
        {t(isPickup ? "deliveryCodeHintPickup" : "deliveryCodeHint")}
      </p>
      <button
        type="button"
        onClick={handleResend}
        disabled={busy}
        className={styles.resend}
      >
        {t("resendCode")}
      </button>
      {note && <span className={styles.note}>{note}</span>}
    </section>
  );
}
