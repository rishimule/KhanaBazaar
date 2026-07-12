"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import Pager from "@/components/Pager";
import { useDebouncedValue } from "@/lib/useDebouncedValue";
import {
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
  const t = useTranslations("Admin.changeRequests");
  const tTitle = useTranslations("Admin.titles");
  const tc = useTranslations("Admin.common");
  const tStatus = useTranslations("Shared.changeRequest");
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
    /* eslint-disable react-hooks/set-state-in-effect -- start loading state synchronously before the async fetch */
    setLoading(true);
    setError(null);
    /* eslint-enable react-hooks/set-state-in-effect */
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
        setError(e instanceof Error ? e.message : t("loadError"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, tab, debouncedQuery, page, t]);

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>{tTitle("changeRequests")}</h1>
      <p className={styles.subtitle}>{t("subtitle")}</p>

      <div className={styles.tabs}>
        <button
          type="button"
          className={tab === "open" ? styles.activeTab : styles.tab}
          onClick={() => {
            setTab("open");
            setPage(1);
          }}
        >
          {t("tabOpen")}
        </button>
        <button
          type="button"
          className={tab === "terminal" ? styles.activeTab : styles.tab}
          onClick={() => {
            setTab("terminal");
            setPage(1);
          }}
        >
          {t("tabHistory")}
        </button>
      </div>

      <input
        type="search"
        className={styles.search}
        placeholder={t("searchPlaceholder")}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setPage(1);
        }}
      />

      {loading && <p className={styles.muted}>{tc("loading")}</p>}
      {error && <p className={styles.error}>{error}</p>}
      {!loading && !error && rows.length === 0 && (
        <p className={styles.muted}>{t("empty")}</p>
      )}

      {rows.length > 0 && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>{t("colSeller")}</th>
              <th>{t("colGroup")}</th>
              <th>{t("colStatus")}</th>
              <th>{t("colSubmissions")}</th>
              <th>{t("colLastActivity")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className={styles.sellerCell}>
                  {r.seller_business_name}
                </td>
                <td>{tStatus(`group_${r.group}`)}</td>
                <td>
                  <span
                    className={`${styles.pill} ${styles[`tone_${r.status}`]}`}
                  >
                    {tStatus(`status_${r.status}`)}
                  </span>
                </td>
                <td>{r.submission_count}</td>
                <td>{new Date(r.updated_at).toLocaleString()}</td>
                <td className={styles.actionCell}>
                  <Link
                    href={`/admin/sellers/${r.seller_user_id}/requests/${r.id}`}
                    className={styles.reviewBtn}
                  >
                    {t("review")} →
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
