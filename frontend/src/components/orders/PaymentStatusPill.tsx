"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import { useTranslations } from "next-intl";
import type { OrderPayment } from "@/types";
import styles from "./PaymentStatusPill.module.css";

const STATUS_CLASS: Record<string, string> = {
  pending: styles.pending,
  paid: styles.paid,
  failed: styles.failed,
  refunded: styles.refunded,
};

interface Props {
  payment: OrderPayment;
  /** Courier: cancelled after payment, refund not yet recorded (spec §10.3). */
  refundDue?: boolean;
}

export default function PaymentStatusPill({ payment, refundDue = false }: Props) {
  const t = useTranslations("Order.payment");
  return (
    <span className={`${styles.pill} ${refundDue ? styles.refundDue : STATUS_CLASS[payment.status] ?? ""}`}>
      <span className={styles.method}>{t(`method.${payment.method}`)}</span>
      <span className={styles.dot}>·</span>
      <span className={styles.status}>
        {refundDue ? t("status.refund_due") : t(`status.${payment.status}`)}
      </span>
    </span>
  );
}
