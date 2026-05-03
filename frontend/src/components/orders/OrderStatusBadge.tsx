import type { OrderStatus } from "@/types";
import styles from "./OrderStatusBadge.module.css";

const LABELS: Record<OrderStatus, string> = {
  pending: "Pending",
  packed: "Packed",
  dispatched: "Dispatched",
  delivered: "Delivered",
  cancelled: "Cancelled",
};

export default function OrderStatusBadge({ status }: { status: OrderStatus }) {
  return <span className={`${styles.badge} ${styles[status]}`}>{LABELS[status]}</span>;
}
