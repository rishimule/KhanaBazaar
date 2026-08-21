"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { adminGetCustomerStoreCredit } from "@/lib/returns";
import type { StoreCreditBalance } from "@/types";
import styles from "./AdminCustomerStoreCredit.module.css";

interface Props {
  customerProfileId: number;
}

/** Read-only: what sellers owe this customer from accepted returns. */
export default function AdminCustomerStoreCredit({ customerProfileId }: Props) {
  const t = useTranslations("Admin.returns");
  const { token } = useAuth();
  const [view, setView] = useState<{
    status: "loading" | "ok" | "error";
    rows: StoreCreditBalance[];
  }>({ status: "loading", rows: [] });

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const rows = await adminGetCustomerStoreCredit(token, customerProfileId);
        if (!cancelled) setView({ status: "ok", rows });
      } catch {
        if (!cancelled) setView({ status: "error", rows: [] });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, customerProfileId]);

  const { status, rows } = view;

  return (
    <section className={styles.card}>
      <h3 className={styles.heading}>{t("storeCreditTitle")}</h3>
      {status === "error" ? (
        <p role="alert" className={styles.error}>
          {t("storeCreditFailed")}
        </p>
      ) : status === "loading" ? (
        <p className={styles.muted}>{t("loading")}</p>
      ) : rows.length === 0 ? (
        <p className={styles.muted}>{t("storeCreditEmpty")}</p>
      ) : (
        <ul className={styles.list}>
          {rows.map((row) => (
            <li key={row.seller_profile_id}>
              <span>{row.store_name}</span>
              <span className={styles.amount}>₹{row.balance.toFixed(2)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
