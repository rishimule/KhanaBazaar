"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import ReturnStatusBadge from "@/components/returns/ReturnStatusBadge";
import { useAuth } from "@/lib/AuthContext";
import { adminListReturns, adminListSellerReturns } from "@/lib/returns";
import type { ReturnRequest, ReturnStatus } from "@/types";
import styles from "./AdminReturnsTable.module.css";

const FILTERS: (ReturnStatus | "all")[] = [
  "all",
  "awaiting_customer_confirmation",
  "active",
  "awaiting_payment_confirmation",
  "closed",
  "rejected",
];

interface Props {
  /** Seller's USER id — scopes to the supervisor hub tab. Omit for the global
   *  list. Matches every other /admin/sellers/{id} route in this app. */
  sellerUserId?: number;
}

export default function AdminReturnsTable({ sellerUserId }: Props) {
  const t = useTranslations("Admin.returns");
  const { token } = useAuth();
  const [filter, setFilter] = useState<ReturnStatus | "all">("all");
  const [view, setView] = useState<{
    status: "loading" | "ok" | "error";
    rows: ReturnRequest[];
  }>({ status: "loading", rows: [] });

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const data = sellerUserId
          ? await adminListSellerReturns(token, sellerUserId)
          : await adminListReturns(token, {
              status: filter === "all" ? undefined : filter,
            });
        if (!cancelled) setView({ status: "ok", rows: data });
      } catch {
        if (!cancelled) setView({ status: "error", rows: [] });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, filter, sellerUserId]);

  const { status, rows } = view;

  return (
    <div className={styles.wrap}>
      <div className={styles.filters} hidden={Boolean(sellerUserId)}>
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
              <th>{t("colOrder")}</th>
              {!sellerUserId && <th>{t("colSeller")}</th>}
              <th>{t("colAmount")}</th>
              <th>{t("colStatus")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <Link href={`/admin/returns/${row.id}`} className={styles.link}>
                    #{row.id}
                  </Link>
                </td>
                <td>#{row.order_id}</td>
                {!sellerUserId && <td>#{row.seller_profile_id}</td>}
                <td className={styles.amount}>₹{row.total_amount.toFixed(2)}</td>
                <td>
                  <ReturnStatusBadge status={row.status} namespace="Admin.returns" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
