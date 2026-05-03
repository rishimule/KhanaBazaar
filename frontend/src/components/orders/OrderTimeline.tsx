import type { OrderStatus } from "@/types";
import styles from "./OrderTimeline.module.css";

const STEPS: { key: OrderStatus; label: string }[] = [
  { key: "pending", label: "Order placed" },
  { key: "packed", label: "Packed" },
  { key: "dispatched", label: "Dispatched" },
  { key: "delivered", label: "Delivered" },
];

const ORDER_INDEX: Record<OrderStatus, number> = {
  pending: 0,
  packed: 1,
  dispatched: 2,
  delivered: 3,
  cancelled: -1,
};

export default function OrderTimeline({ status }: { status: OrderStatus }) {
  if (status === "cancelled") {
    return <div className={styles.cancelled}>Order cancelled</div>;
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
            <span className={styles.label}>{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}
