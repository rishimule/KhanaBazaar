"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import type { OrderStatus } from "@/types";
import styles from "./OrderStatusBadge.module.css";

export default function OrderStatusBadge({ status }: { status: OrderStatus }) {
  const t = useTranslations("Order.status");
  return <span className={`${styles.badge} ${styles[status]}`}>{t(status)}</span>;
}
