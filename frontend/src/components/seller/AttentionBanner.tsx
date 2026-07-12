"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import { useTranslations } from "next-intl";
import type { OrderStatusCounts } from "@/types";
import styles from "./AttentionBanner.module.css";

interface Props {
  activeOrders: number;
  counts: OrderStatusCounts;
}

export default function AttentionBanner({ activeOrders, counts }: Props) {
  const t = useTranslations("Seller.dashboard");
  if (activeOrders <= 0) return null;
  const parts: string[] = [];
  if (counts.packed > 0) parts.push(t("attnPacked", { count: counts.packed }));
  if (counts.pending > 0) parts.push(t("attnPending", { count: counts.pending }));
  if (counts.dispatched > 0) parts.push(t("attnDispatched", { count: counts.dispatched }));
  const detail = parts.length > 0 ? ` — ${parts.join(", ")}.` : ".";

  return (
    <div className={styles.banner}>
      <span className={styles.icon}>⚠️</span>
      <span className={styles.text}>
        <strong>{t("attnHeadline", { count: activeOrders })}</strong>
        {detail}
      </span>
      <Link href="/seller/orders" className={styles.link}>
        {t("reviewOrders")} →
      </Link>
    </div>
  );
}
