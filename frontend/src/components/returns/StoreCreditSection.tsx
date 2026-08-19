"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { getStoreCreditLedger, listStoreCredit } from "@/lib/returns";
import type { StoreCreditBalance, StoreCreditEntry } from "@/types";
import styles from "./StoreCreditSection.module.css";

/**
 * Store credit a seller owes THIS customer, from accepted returns.
 *
 * Deliberately a separate section from the postpaid credit on the same page:
 * one is money the customer is owed, the other money they owe. Merging them
 * would be actively misleading.
 */
export default function StoreCreditSection() {
  const t = useTranslations("Account.storeCredit");
  const { token } = useAuth();
  const [balances, setBalances] = useState<StoreCreditBalance[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [openSeller, setOpenSeller] = useState<number | null>(null);
  const [ledger, setLedger] = useState<StoreCreditEntry[]>([]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await listStoreCredit(token);
        if (!cancelled) setBalances(data);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const openLedger = async (sellerProfileId: number) => {
    if (!token) return;
    if (openSeller === sellerProfileId) {
      setOpenSeller(null);
      return;
    }
    setOpenSeller(sellerProfileId);
    try {
      setLedger(await getStoreCreditLedger(token, sellerProfileId));
    } catch {
      setLedger([]);
    }
  };

  if (failed) {
    return (
      <section className={styles.section}>
        <h2 className={styles.heading}>{t("heading")}</h2>
        <p role="alert" className={styles.error}>
          {t("loadFailed")}
        </p>
      </section>
    );
  }
  if (!balances) return null;

  return (
    <section className={styles.section}>
      <h2 className={styles.heading}>{t("heading")}</h2>
      <p className={styles.muted}>{t("intro")}</p>
      {balances.length === 0 ? (
        <p className={styles.muted}>{t("empty")}</p>
      ) : (
        <ul className={styles.list}>
          {balances.map((b) => (
            <li key={b.seller_profile_id} className={styles.card}>
              <div className={styles.cardHead}>
                <span className={styles.store}>{b.store_name}</span>
                <span className={styles.balance}>₹{b.balance.toFixed(2)}</span>
              </div>
              <p className={styles.muted}>
                {t("lifetime", {
                  earned: b.lifetime_earned.toFixed(2),
                  spent: b.lifetime_spent.toFixed(2),
                })}
              </p>
              <button
                type="button"
                className={styles.linkButton}
                onClick={() => openLedger(b.seller_profile_id)}
              >
                {openSeller === b.seller_profile_id ? t("hideHistory") : t("showHistory")}
              </button>
              {openSeller === b.seller_profile_id && (
                <ul className={styles.ledger}>
                  {ledger.length === 0 && (
                    <li className={styles.muted}>{t("noHistory")}</li>
                  )}
                  {ledger.map((entry) => (
                    <li key={entry.id}>
                      <span>{t(`entry.${entry.entry_type}`)}</span>
                      <span
                        className={entry.amount < 0 ? styles.negative : styles.positive}
                      >
                        {entry.amount < 0 ? "−" : "+"}₹
                        {Math.abs(entry.amount).toFixed(2)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
