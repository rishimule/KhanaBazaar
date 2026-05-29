"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import type { OrderStatusCounts } from "@/types";
import styles from "./AttentionBanner.module.css";

interface Props {
  activeOrders: number;
  counts: OrderStatusCounts;
}

export default function AttentionBanner({ activeOrders, counts }: Props) {
  if (activeOrders <= 0) return null;
  const parts: string[] = [];
  if (counts.packed > 0) parts.push(`${counts.packed} packed and awaiting pickup`);
  if (counts.pending > 0) parts.push(`${counts.pending} pending acceptance`);
  if (counts.dispatched > 0) parts.push(`${counts.dispatched} out for delivery`);
  const detail = parts.length > 0 ? ` — ${parts.join(", ")}.` : ".";

  return (
    <div className={styles.banner}>
      <span className={styles.icon}>⚠️</span>
      <span className={styles.text}>
        <strong>
          {activeOrders} active {activeOrders === 1 ? "order needs" : "orders need"} attention
        </strong>
        {detail}
      </span>
      <Link href="/seller/orders" className={styles.link}>
        Review orders →
      </Link>
    </div>
  );
}
