"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import {
  GROUP_LABEL,
  STATUS_TONE,
  adminListSellerCRs,
} from "@/lib/changeRequests";
import type { SellerProfileChangeRequest } from "@/types";
import styles from "./page.module.css";

type Tab = "open" | "terminal";

/**
 * Admin per-seller change-request index. Split into Open and History tabs.
 *
 * Open tab columns: Group · Submitted at · Submissions · Last seller note · Review
 * History columns:  Group · Outcome · Decided at · Decided by · View
 *
 * Rows are sorted newest-first by the backend.
 */
export default function AdminSellerRequestsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const sellerId = Number(id);
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
    if (!token || !Number.isFinite(sellerId)) return;
    let cancelled = false;
    adminListSellerCRs(token, sellerId, tab)
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
  }, [token, sellerId, tab]);

  const rows = rowsByTab[tab];
  const error = errorByTab[tab] ?? null;
  const loading = rows === undefined && error === null;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>{tCR("indexTitle")}</h1>
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
        <div className={styles.tableWrap}>
          {tab === "open" ? (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Group</th>
                  <th>Submitted</th>
                  <th>Submissions</th>
                  <th>Last seller note</th>
                  <th aria-label="Review" />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <span className={styles.group}>{GROUP_LABEL[r.group]}</span>
                      <span
                        className={`${styles.pill} ${styles[`tone_${STATUS_TONE[r.status]}`]}`}
                      >
                        {tStatus(`status_${r.status}`)}
                      </span>
                    </td>
                    <td className={styles.time}>
                      {new Date(r.created_at).toLocaleString()}
                    </td>
                    <td>{r.submission_count}</td>
                    <td className={styles.note}>
                      {lastSellerNote(r) ?? "—"}
                    </td>
                    <td>
                      <Link
                        href={`/admin/sellers/${sellerId}/requests/${r.id}`}
                        className={styles.actionLink}
                      >
                        Review →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Group</th>
                  <th>Outcome</th>
                  <th>Decided at</th>
                  <th>Decided by</th>
                  <th aria-label="View" />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <span className={styles.group}>{GROUP_LABEL[r.group]}</span>
                    </td>
                    <td>
                      <span
                        className={`${styles.pill} ${styles[`tone_${STATUS_TONE[r.status]}`]}`}
                      >
                        {tStatus(`status_${r.status}`)}
                      </span>
                    </td>
                    <td className={styles.time}>
                      {r.decided_at
                        ? new Date(r.decided_at).toLocaleString()
                        : "—"}
                    </td>
                    <td>
                      {r.decided_by_user_id != null
                        ? `User #${r.decided_by_user_id}`
                        : "—"}
                    </td>
                    <td>
                      <Link
                        href={`/admin/sellers/${sellerId}/requests/${r.id}`}
                        className={styles.actionLink}
                      >
                        View →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

/** Returns the latest seller-authored note from the timeline, if any. */
function lastSellerNote(cr: SellerProfileChangeRequest): string | null {
  // Events are ordered oldest-first; iterate from the end for the latest one.
  for (let i = cr.events.length - 1; i >= 0; i -= 1) {
    const ev = cr.events[i];
    if (ev.actor_role === "seller" && ev.note) {
      return ev.note;
    }
  }
  return null;
}
