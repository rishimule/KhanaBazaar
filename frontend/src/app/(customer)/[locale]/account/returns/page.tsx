"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import ReturnStatusBadge from "@/components/returns/ReturnStatusBadge";
import { useAuth } from "@/lib/AuthContext";
import { listReturns } from "@/lib/returns";
import type { ReturnRequest } from "@/types";
import styles from "./page.module.css";

export default function ReturnsListPage() {
  const t = useTranslations("Account.returns");
  const { token } = useAuth();
  const [rows, setRows] = useState<ReturnRequest[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await listReturns(token);
        if (!cancelled) setRows(data);
      } catch {
        // A failed fetch must not render as "you have no returns".
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (failed) {
    return (
      <p role="alert" className={styles.error}>
        {t("loadFailed")}
      </p>
    );
  }
  if (!rows) return <p className={styles.muted}>{t("loading")}</p>;
  if (rows.length === 0) return <p className={styles.muted}>{t("empty")}</p>;

  return (
    <ul className={styles.list}>
      {rows.map((row) => (
        <li key={row.id} className={styles.row}>
          <Link href={`/account/returns/${row.id}`} className={styles.rowLink}>
            <div className={styles.rowMain}>
              <span className={styles.rowTitle}>
                {t("rowTitle", { id: row.id, orderId: row.order_id })}
              </span>
              <span className={styles.rowMeta}>
                {row.items.length === 1
                  ? row.items[0].product_name
                  : t("itemCount", { count: row.items.length })}
              </span>
            </div>
            <div className={styles.rowSide}>
              <span className={styles.amount}>₹{row.total_amount.toFixed(2)}</span>
              <ReturnStatusBadge status={row.status} />
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
