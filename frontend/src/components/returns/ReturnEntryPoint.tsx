"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import ReturnStatusBadge from "@/components/returns/ReturnStatusBadge";
import { useAuth } from "@/lib/AuthContext";
import { getReturnEligibility, listReturns } from "@/lib/returns";
import type { Order, ReturnEligibility, ReturnRequest } from "@/types";
import styles from "./ReturnEntryPoint.module.css";

interface Props {
  order: Order;
}

/**
 * Return affordance on the order detail page: existing returns for this order,
 * plus a "Return items" link when anything is still returnable.
 *
 * Renders nothing at all for an order that was never delivered, and renders
 * nothing on a failed fetch rather than a misleading "not returnable" message.
 */
export default function ReturnEntryPoint({ order }: Props) {
  const t = useTranslations("Account.returns");
  const { token } = useAuth();
  const [eligibility, setEligibility] = useState<ReturnEligibility | null>(null);
  const [existing, setExisting] = useState<ReturnRequest[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!token || order.status !== "delivered") return;
    let cancelled = false;
    (async () => {
      try {
        const [elig, mine] = await Promise.all([
          getReturnEligibility(token, order.id),
          listReturns(token),
        ]);
        if (cancelled) return;
        setEligibility(elig);
        setExisting(mine.filter((r) => r.order_id === order.id));
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, order.id, order.status]);

  if (order.status !== "delivered" || failed || !eligibility) return null;

  return (
    <section className={styles.panel}>
      <h2 className={styles.title}>{t("panelTitle")}</h2>

      {existing.length > 0 && (
        <ul className={styles.existing}>
          {existing.map((r) => (
            <li key={r.id}>
              <Link href={`/account/returns/${r.id}`} className={styles.existingLink}>
                <span>{t("rowTitle", { id: r.id, orderId: r.order_id })}</span>
                <ReturnStatusBadge status={r.status} />
              </Link>
            </li>
          ))}
        </ul>
      )}

      {eligibility.eligible ? (
        <Link
          href={`/account/orders/${order.id}/return`}
          className="btn btn-primary"
        >
          {t("startReturn")}
        </Link>
      ) : (
        <p className={styles.muted}>
          {t(`ineligible.${eligibility.reason_code ?? "unknown"}`)}
        </p>
      )}
    </section>
  );
}
