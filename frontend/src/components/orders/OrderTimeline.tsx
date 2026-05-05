"use client";

import { useTranslations } from "next-intl";
import type { OrderStatus } from "@/types";
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

export default function OrderTimeline({ status }: { status: OrderStatus }) {
  const t = useTranslations("Order.timeline");
  if (status === "cancelled") {
    return <div className={styles.cancelled}>{t("cancelled")}</div>;
  }
  const current = ORDER_INDEX[status];
  return (
    <ol className={styles.timeline}>
      {STEPS.map((step, idx) => {
        const completed = idx <= current;
        return (
          <li
            key={step.key}
            className={`${styles.step} ${completed ? styles.completed : ""}`}
          >
            <span className={styles.dot} />
            <span className={styles.label}>{t(step.labelKey)}</span>
          </li>
        );
      })}
    </ol>
  );
}
