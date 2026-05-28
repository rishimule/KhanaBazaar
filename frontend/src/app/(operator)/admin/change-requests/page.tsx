"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/AuthContext";
import Pager from "@/components/Pager";
import { useDebouncedValue } from "@/lib/useDebouncedValue";
import {
  GROUP_LABEL,
  adminListAllChangeRequests,
  type AdminQueueRow,
} from "@/lib/changeRequests";
import styles from "./page.module.css";

const PAGE_SIZE = 20;

/**
 * Cross-seller triage queue for profile change requests. Lists all CRs (open
 * by default), ordered by most-recent activity. Each row links to the
 * existing per-seller CR detail page so the approve/edit/reject flow stays
 * unchanged.
 */
export default function AdminCRQueuePage() {
  const { token } = useAuth();
  const [tab, setTab] = useState<"open" | "terminal">("open");
  const [rows, setRows] = useState<AdminQueueRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const debouncedQuery = useDebouncedValue(query, 300);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    adminListAllChangeRequests(token, tab, {
      q: debouncedQuery,
      page,
      page_size: PAGE_SIZE,
    })
      .then((data) => {
        if (cancelled) return;
        setRows(data.items);
        setTotal(data.total);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Failed to load");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, tab, debouncedQuery, page]);

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Change requests</h1>
      <p className={styles.subtitle}>
        Cross-seller triage queue. Click a row to review and decide.
      </p>

      <div className={styles.tabs}>
        <button
          type="button"
          className={tab === "open" ? styles.activeTab : styles.tab}
          onClick={() => {
            setTab("open");
            setPage(1);
          }}
        >
          Open
        </button>
        <button
          type="button"
          className={tab === "terminal" ? styles.activeTab : styles.tab}
          onClick={() => {
            setTab("terminal");
            setPage(1);
          }}
        >
          History
        </button>
      </div>

      <input
        type="search"
        className={styles.search}
        placeholder="Search by seller business name…"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setPage(1);
        }}
      />

      {loading && <p className={styles.muted}>Loading…</p>}
      {error && <p className={styles.error}>{error}</p>}
      {!loading && !error && rows.length === 0 && (
        <p className={styles.muted}>No requests in this tab.</p>
      )}

      {rows.length > 0 && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Seller</th>
              <th>Group</th>
              <th>Status</th>
              <th>Submissions</th>
              <th>Last activity</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className={styles.sellerCell}>
                  {r.seller_business_name}
                </td>
                <td>{GROUP_LABEL[r.group]}</td>
                <td>
                  <span
                    className={`${styles.pill} ${styles[`tone_${r.status}`]}`}
                  >
                    {r.status.replace("_", " ")}
                  </span>
                </td>
                <td>{r.submission_count}</td>
                <td>{new Date(r.updated_at).toLocaleString()}</td>
                <td className={styles.actionCell}>
                  <Link
                    href={`/admin/sellers/${r.seller_user_id}/requests/${r.id}`}
                    className={styles.reviewBtn}
                  >
                    Review →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Pager page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} />
    </div>
  );
}
