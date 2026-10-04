"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import type { DeliveryMode, OrderStatus } from "@/types";
import styles from "./OrderStatusBadge.module.css";

export default function OrderStatusBadge({
  status,
  deliveryMode,
  audience = "operator",
}: {
  status: OrderStatus;
  deliveryMode?: DeliveryMode;
  /** Courier `quoted` reads "Quote ready" to the customer, "Quote sent" to operators. */
  audience?: "customer" | "operator";
}) {
  const t = useTranslations("Order.status");
  let key: string = status;
  if (deliveryMode === "pickup" && (status === "dispatched" || status === "delivered")) {
    // Pickup reuses the same statuses; only the customer-facing wording differs.
    key = `pickup_${status}`;
  } else if (deliveryMode === "courier" && status !== "packed" && status !== "delivered" && status !== "cancelled") {
    key = status === "quoted" && audience === "customer" ? "courier_quoted_customer" : `courier_${status}`;
  }
  return <span className={`${styles.badge} ${styles[status]}`}>{t(key)}</span>;
}
