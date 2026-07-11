"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import type { DeliveryMode, OrderStatus } from "@/types";
import styles from "./OrderStatusBadge.module.css";

export default function OrderStatusBadge({
  status,
  deliveryMode,
}: {
  status: OrderStatus;
  deliveryMode?: DeliveryMode;
}) {
  const t = useTranslations("Order.status");
  // Pickup reuses the same statuses; only the customer-facing wording differs.
  const key =
    deliveryMode === "pickup" && (status === "dispatched" || status === "delivered")
      ? `pickup_${status}`
      : status;
  return <span className={`${styles.badge} ${styles[status]}`}>{t(key)}</span>;
}
