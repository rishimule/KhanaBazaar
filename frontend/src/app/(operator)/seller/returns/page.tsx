"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import ReturnStatusBadge from "@/components/returns/ReturnStatusBadge";
import { useAuth } from "@/lib/AuthContext";
import { listSellerReturns } from "@/lib/returns";
import type { ReturnRequest, ReturnStatus } from "@/types";
import styles from "./page.module.css";

const FILTERS: (ReturnStatus | "all")[] = [
  "active",
  "awaiting_customer_confirmation",
  "awaiting_payment_confirmation",
  "closed",
  "rejected",
  "all",
];

export default function SellerReturnsPage() {
  const t = useTranslations("Seller.returns");
  const { token } = useAuth();
  const [filter, setFilter] = useState<ReturnStatus | "all">("active");
  // One state value rather than separate rows/failed resets: setting state
  // synchronously inside the effect triggers cascading renders (and trips the
  // lint rule). The previous list stays on screen until the new one lands.
  const [view, setView] = useState<{
    status: "loading" | "ok" | "error";
    rows: ReturnRequest[];
  }>({ status: "loading", rows: [] });

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await listSellerReturns(
          token,
          filter === "all" ? undefined : filter
        );
        if (!cancelled) setView({ status: "ok", rows: data });
      } catch {
        // Never show "no returns" for a failed fetch — that would tell a seller
        // nobody is waiting when somebody is.
        if (!cancelled) setView({ status: "error", rows: [] });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, filter]);

  const { status, rows } = view;

  return (
    <div className={styles.page}>
      <div className={styles.filters}>
        {FILTERS.map((f) => (
          <button
            key={f}
            type="button"
            className={`${styles.filter} ${filter === f ? styles.filterOn : ""}`}
            onClick={() => setFilter(f)}
          >
            {f === "all" ? t("filterAll") : t(`status.${f}`)}
          </button>
        ))}
      </div>

      {status === "error" ? (
        <p role="alert" className={styles.error}>
          {t("loadFailed")}
        </p>
      ) : status === "loading" ? (
        <p className={styles.muted}>{t("loading")}</p>
      ) : rows.length === 0 ? (
        <p className={styles.muted}>{t("empty")}</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>{t("colReturn")}</th>
              <th>{t("colItems")}</th>
              <th>{t("colAmount")}</th>
              <th>{t("colStatus")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <Link href={`/seller/returns/${row.id}`} className={styles.link}>
                    #{row.id}
                  </Link>
                  <span className={styles.sub}>
                    {t("orderRef", { orderId: row.order_id })}
                  </span>
                </td>
                <td>
                  {row.items.length === 1
                    ? row.items[0].product_name
                    : t("itemCount", { count: row.items.length })}
                </td>
                <td className={styles.amount}>₹{row.total_amount.toFixed(2)}</td>
                <td>
                  <ReturnStatusBadge status={row.status} namespace="Seller.returns" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
