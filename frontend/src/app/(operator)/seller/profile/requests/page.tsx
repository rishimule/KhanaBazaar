"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import {
  GROUP_LABEL,
  STATUS_TONE,
  listMyChangeRequests,
} from "@/lib/changeRequests";
import type { SellerProfileChangeRequest } from "@/types";
import styles from "./page.module.css";

type Tab = "open" | "terminal";

/**
 * Seller-facing index of profile change requests, split into Open and
 * History tabs. Each row links to the detail page where the seller can
 * inspect, withdraw, or resubmit.
 */
export default function SellerRequestsPage() {
  const { token } = useAuth();
  const tCR = useTranslations("Seller.changeRequests");
  const tStatus = useTranslations("Shared.changeRequest");
  const [tab, setTab] = useState<Tab>("open");
  const [rowsByTab, setRowsByTab] = useState<
    Partial<Record<Tab, SellerProfileChangeRequest[]>>
  >({});
  const [errorByTab, setErrorByTab] = useState<
    Partial<Record<Tab, string | null>>
  >({});

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    listMyChangeRequests(token, tab)
      .then((data) => {
        if (cancelled) return;
        setRowsByTab((m) => ({ ...m, [tab]: data }));
        setErrorByTab((m) => ({ ...m, [tab]: null }));
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setErrorByTab((m) => ({
          ...m,
          [tab]: e instanceof Error ? e.message : "Failed to load requests",
        }));
      });
    return () => {
      cancelled = true;
    };
  }, [token, tab]);

  const rows = rowsByTab[tab];
  const error = errorByTab[tab] ?? null;
  const loading = rows === undefined && error === null;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>{tCR("indexTitle")}</h1>
        <Link href="/seller/profile" className={styles.backLink}>
          ← Back to profile
        </Link>
      </header>

      <div className={styles.tabs} role="tablist" aria-label="Request status">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "open"}
          className={`${styles.tab} ${tab === "open" ? styles.activeTab : ""}`}
          onClick={() => setTab("open")}
        >
          {tCR("tabOpen")}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "terminal"}
          className={`${styles.tab} ${
            tab === "terminal" ? styles.activeTab : ""
          }`}
          onClick={() => setTab("terminal")}
        >
          {tCR("tabHistory")}
        </button>
      </div>

      {loading && <p className={styles.muted}>Loading…</p>}
      {error && <p className={styles.error}>{error}</p>}
      {!loading && !error && rows !== undefined && rows.length === 0 && (
        <p className={styles.empty}>{tCR("noOpen")}</p>
      )}

      {!loading && !error && rows !== undefined && rows.length > 0 && (
        <ul className={styles.list}>
          {rows.map((r) => (
            <li key={r.id} className={styles.row}>
              <span className={styles.group}>{GROUP_LABEL[r.group]}</span>
              <span
                className={`${styles.pill} ${styles[`tone_${STATUS_TONE[r.status]}`]}`}
              >
                {tStatus(`status_${r.status}`)}
              </span>
              <span className={styles.time}>
                {new Date(r.updated_at).toLocaleString()}
              </span>
              <Link
                href={`/seller/profile/requests/${r.id}`}
                className={styles.viewLink}
              >
                View →
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
