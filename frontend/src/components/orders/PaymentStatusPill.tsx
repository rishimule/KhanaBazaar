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
}

export default function PaymentStatusPill({ payment }: Props) {
  const t = useTranslations("Order.payment");
  return (
    <span className={`${styles.pill} ${STATUS_CLASS[payment.status] ?? ""}`}>
      <span className={styles.method}>{payment.method.toUpperCase()}</span>
      <span className={styles.dot}>·</span>
      <span className={styles.status}>{t(`status.${payment.status}`)}</span>
    </span>
  );
}
