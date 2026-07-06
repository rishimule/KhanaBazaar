// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import Link from "next/link";

import styles from "./ReportsUpsellCard.module.css";

// Shown in place of the RevenueChart when the store is not premium (reports are
// gated — /sellers/me/revenue-series returns 403 reports_premium_only).
export default function ReportsUpsellCard() {
  return (
    <section className={styles.card}>
      <div className={styles.lock} aria-hidden>
        🔒
      </div>
      <h3 className={styles.title}>Advanced revenue reports</h3>
      <p className={styles.body}>
        Upgrade to a paid plan to unlock revenue trends, daily averages, and
        peak-day insights for your store.
      </p>
      <Link href="/seller/plan" className="btn btn-primary">
        View plans
      </Link>
    </section>
  );
}
