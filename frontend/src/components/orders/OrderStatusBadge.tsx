"use client";

import { useTranslations } from "next-intl";
import type { OrderStatus } from "@/types";
import styles from "./OrderStatusBadge.module.css";

export default function OrderStatusBadge({ status }: { status: OrderStatus }) {
  const t = useTranslations("Order.status");
  return <span className={`${styles.badge} ${styles[status]}`}>{t(status)}</span>;
}
