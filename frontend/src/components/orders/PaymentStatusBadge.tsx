// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import styles from "./PaymentStatusBadge.module.css";

type Status = "pending" | "paid" | "failed" | "refunded";

const LABEL: Record<Status, string> = {
  pending: "Payment pending",
  paid: "Paid",
  failed: "Payment failed",
  refunded: "Refunded",
};

export default function PaymentStatusBadge({ status }: { status: string }) {
  const s = (status as Status) in LABEL ? (status as Status) : "pending";
  return <span className={`${styles.badge} ${styles[s]}`}>{LABEL[s]}</span>;
}
