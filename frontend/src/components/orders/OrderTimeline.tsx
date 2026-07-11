"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import type { DeliveryMode, OrderStatus } from "@/types";
import styles from "./OrderTimeline.module.css";

const STEPS: { key: OrderStatus; labelKey: string }[] = [
  { key: "pending", labelKey: "placed" },
  { key: "packed", labelKey: "packed" },
  { key: "dispatched", labelKey: "dispatched" },
  { key: "delivered", labelKey: "delivered" },
];

const ORDER_INDEX: Record<OrderStatus, number> = {
  pending: 0,
  packed: 1,
  dispatched: 2,
  delivered: 3,
  cancelled: -1,
};

export default function OrderTimeline({
  status,
  deliveryMode,
}: {
  status: OrderStatus;
  deliveryMode?: DeliveryMode;
}) {
  const t = useTranslations("Order.timeline");
  if (status === "cancelled") {
    return <div className={styles.cancelled}>{t("cancelled")}</div>;
  }
  const current = ORDER_INDEX[status];
  const isPickup = deliveryMode === "pickup";
  return (
    <ol className={styles.timeline}>
      {STEPS.map((step, idx) => {
        const completed = idx <= current;
        const labelKey =
          isPickup && (step.key === "dispatched" || step.key === "delivered")
            ? `pickup_${step.key}`
            : step.labelKey;
        return (
          <li
            key={step.key}
            className={`${styles.step} ${completed ? styles.completed : ""}`}
          >
            <span className={styles.dot} />
            <span className={styles.label}>{t(labelKey)}</span>
          </li>
        );
      })}
    </ol>
  );
}
