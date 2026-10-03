"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import type { DeliveryMode, OrderStatus } from "@/types";
import styles from "./OrderTimeline.module.css";

type Step = { labelKey: string; reachedAt: number };

const LOCAL_STEPS: Step[] = [
  { labelKey: "placed", reachedAt: 0 },
  { labelKey: "packed", reachedAt: 1 },
  { labelKey: "dispatched", reachedAt: 2 },
  { labelKey: "delivered", reachedAt: 3 },
];
const LOCAL_INDEX: Record<OrderStatus, number> = {
  pending: 0, quoted: 0, accepted: 0, paid: 0,
  packed: 1, dispatched: 2, delivered: 3, cancelled: -1,
};

// Courier: Requested → Quote → Paid → Packed → Shipped → Delivered (spec §14).
const COURIER_STEPS: Step[] = [
  { labelKey: "courier_requested", reachedAt: 0 },
  { labelKey: "courier_quote", reachedAt: 1 },
  { labelKey: "courier_paid", reachedAt: 2 },
  { labelKey: "packed", reachedAt: 3 },
  { labelKey: "courier_shipped", reachedAt: 4 },
  { labelKey: "delivered", reachedAt: 5 },
];
const COURIER_INDEX: Record<OrderStatus, number> = {
  pending: 0, quoted: 1, accepted: 1, paid: 2,
  packed: 3, dispatched: 4, delivered: 5, cancelled: -1,
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
  const isCourier = deliveryMode === "courier";
  const isPickup = deliveryMode === "pickup";
  const steps = isCourier ? COURIER_STEPS : LOCAL_STEPS;
  const current = (isCourier ? COURIER_INDEX : LOCAL_INDEX)[status];
  return (
    <ol className={styles.timeline}>
      {steps.map((step) => {
        const completed = step.reachedAt <= current;
        const labelKey =
          isPickup && (step.labelKey === "dispatched" || step.labelKey === "delivered")
            ? `pickup_${step.labelKey}`
            : step.labelKey;
        return (
          <li key={step.labelKey} className={`${styles.step} ${completed ? styles.completed : ""}`}>
            <span className={styles.dot} />
            <span className={styles.label}>{t(labelKey)}</span>
          </li>
        );
      })}
    </ol>
  );
}
