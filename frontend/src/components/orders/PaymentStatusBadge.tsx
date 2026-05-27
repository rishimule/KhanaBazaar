"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useTranslations } from "next-intl";
import styles from "./PaymentStatusBadge.module.css";

type Status = "pending" | "paid" | "failed" | "refunded";

const STATUS_KEY: Record<Status, string> = {
  pending: "pending",
  paid: "paid",
  failed: "failed",
  refunded: "refunded",
};

export default function PaymentStatusBadge({ status }: { status: string }) {
  const t = useTranslations("Shared");
  const s = (status as Status) in STATUS_KEY ? (status as Status) : "pending";
  return (
    <span className={`${styles.badge} ${styles[s]}`}>
      {t(`paymentStatus.${STATUS_KEY[s]}`)}
    </span>
  );
}
