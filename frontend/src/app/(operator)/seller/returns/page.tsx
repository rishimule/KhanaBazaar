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
  const [rows, setRows] = useState<ReturnRequest[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setRows(null);
    setFailed(false);
    (async () => {
      try {
        const data = await listSellerReturns(
          token,
          filter === "all" ? undefined : filter
        );
        if (!cancelled) setRows(data);
      } catch {
        // Never show "no returns" for a failed fetch — that would tell a seller
        // nobody is waiting when somebody is.
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, filter]);

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

      {failed ? (
        <p role="alert" className={styles.error}>
          {t("loadFailed")}
        </p>
      ) : !rows ? (
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
