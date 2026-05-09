"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useTranslations } from "next-intl";
import OrderStatusBadge from "./OrderStatusBadge";
import type { Order, UserRole } from "@/types";
import styles from "./OrderCard.module.css";

interface Props {
  order: Order;
  role: UserRole;
}

const HREF_BY_ROLE: Record<UserRole, (id: number) => string> = {
  customer: (id) => `/account/orders/${id}`,
  seller: (id) => `/seller/orders/${id}`,
  admin: (id) => `/admin/orders/${id}`,
};

function relativeTime(
  iso: string,
  t: (key: string, values?: Record<string, string | number | Date>) => string,
): string {
  const then = new Date(iso).getTime();
  const diffSec = Math.round((Date.now() - then) / 1000);
  if (diffSec < 60) return t("secondsAgo", { count: diffSec });
  const min = Math.round(diffSec / 60);
  if (min < 60) return t("minutesAgo", { count: min });
  const hr = Math.round(min / 60);
  if (hr < 24) return t("hoursAgo", { count: hr });
  return t("daysAgo", { count: Math.round(hr / 24) });
}

export default function OrderCard({ order, role }: Props) {
  const t = useTranslations("Order.card");
  const href = HREF_BY_ROLE[role](order.id);
  return (
    <Link href={href} className={styles.card}>
      <div className={styles.header}>
        <span className={styles.id}>#{order.id}</span>
        <OrderStatusBadge status={order.status} />
      </div>
      <div className={styles.title}>{order.store_name}</div>
      {order.customer_name && (
        <div className={styles.subtitle}>{t("forCustomer", { name: order.customer_name })}</div>
      )}
      <div className={styles.meta}>
        <span className={styles.total}>₹{order.total.toFixed(2)}</span>
        <span className={styles.time}>{relativeTime(order.placed_at, t)}</span>
      </div>
    </Link>
  );
}
