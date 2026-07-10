"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { useAuth } from "@/lib/AuthContext";
import { type CustomerCreditAccount, getMyCredit } from "@/lib/credit";
import styles from "./page.module.css";

const money = (n: number) => `₹${n.toFixed(2)}`;

export default function AccountCreditPage() {
  const t = useTranslations("Credit");
  const { token } = useAuth();
  const [accounts, setAccounts] = useState<CustomerCreditAccount[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    getMyCredit(token)
      .then(setAccounts)
      .catch(() => setAccounts([]))
      .finally(() => setLoading(false));
  }, [token]);

  return (
    <div className={styles.page}>
      <p className={styles.intro}>{t("myIntro")}</p>
      {loading ? (
        <p className={styles.muted}>{t("loading")}</p>
      ) : accounts.length === 0 ? (
        <p className={styles.muted}>{t("myEmpty")}</p>
      ) : (
        accounts.map((a) => (
          <section key={a.seller_profile_id} className={styles.card}>
            <div className={styles.cardHead}>
              <h2 className={styles.storeName}>{a.store_name}</h2>
              <span className={a.status === "active" ? styles.chipActive : styles.chipSuspended}>
                {t(`status_${a.status}`)}
              </span>
            </div>
            <div className={styles.stats}>
              <div className={styles.stat}>
                <span className={styles.statLabel}>{t("colLimit")}</span>
                <span className={styles.statValue}>{money(a.credit_limit)}</span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statLabel}>{t("colOutstanding")}</span>
                <span className={styles.statValue}>{money(a.outstanding_balance)}</span>
              </div>
              <div className={styles.statHighlight}>
                <span className={styles.statLabel}>{t("colAvailable")}</span>
                <span className={styles.statValueStrong}>{money(a.available)}</span>
              </div>
            </div>
          </section>
        ))
      )}
    </div>
  );
}
