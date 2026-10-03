"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import { useTranslations } from "next-intl";
import type { OrderStatusCounts } from "@/types";
import styles from "./AttentionBanner.module.css";

interface Props {
  counts: OrderStatusCounts;
  /** Courier orders whose customer says they paid (seller must check). */
  paymentChecks?: number;
}

/** Only orders waiting on the seller count. On courier orders `quoted` and an
 *  unclaimed `accepted` wait on the customer, so they are left out; a claimed
 *  one is the seller's turn (check the money), hence `paymentChecks`. */
export default function AttentionBanner({ counts, paymentChecks = 0 }: Props) {
  const t = useTranslations("Seller.dashboard");
  const paid = counts.paid ?? 0;
  const total = counts.pending + counts.packed + counts.dispatched + paid + paymentChecks;
  if (total <= 0) return null;
  const parts: string[] = [];
  if (counts.packed > 0) parts.push(t("attnPacked", { count: counts.packed }));
  if (counts.pending > 0) parts.push(t("attnPending", { count: counts.pending }));
  if (paymentChecks > 0) parts.push(t("attnPaymentCheck", { count: paymentChecks }));
  if (paid > 0) parts.push(t("attnPaid", { count: paid }));
  if (counts.dispatched > 0) parts.push(t("attnDispatched", { count: counts.dispatched }));
  const detail = ` — ${parts.join(", ")}.`;

  return (
    <div className={styles.banner}>
      <span className={styles.icon}>⚠️</span>
      <span className={styles.text}>
        <strong>{t("attnHeadline", { count: total })}</strong>
        {detail}
      </span>
      <Link href="/seller/orders" className={styles.link}>
        {t("reviewOrders")} →
      </Link>
    </div>
  );
}
