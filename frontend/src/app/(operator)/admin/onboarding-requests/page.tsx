"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
//
// Admin review list for visitor-submitted seller-onboarding leads.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import DataTable, { Column } from "@/components/DataTable";
import Pager from "@/components/Pager";
import { usePagedList } from "@/lib/usePagedList";
import { useDebouncedValue } from "@/lib/useDebouncedValue";
import { useAuth } from "@/lib/AuthContext";
import {
  adminListOnboardingRequests,
  adminUpdateOnboardingStatus,
} from "@/lib/onboarding";
import type {
  OnboardingRequestStatus,
  PagedResponse,
  SellerOnboardingRequest,
} from "@/types";
import styles from "./page.module.css";
import mobileStyles from "@/components/DataTableCard.module.css";

const PAGE_SIZE = 20;
const STATUSES: OnboardingRequestStatus[] = [
  "new",
  "contacted",
  "onboarded",
  "dismissed",
];

export default function AdminOnboardingRequestsPage() {
  const t = useTranslations("Admin.onboarding");
  const tc = useTranslations("Admin.common");
  const router = useRouter();
  const { dbUser, token, loading: authLoading } = useAuth();

  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const debouncedQuery = useDebouncedValue(query, 300);

  useEffect(() => {
    if (!authLoading && (!dbUser || dbUser.role !== "admin")) {
      router.push(dbUser ? "/" : "/login");
    }
  }, [authLoading, dbUser, router]);

  const fetcher = useCallback(() => {
    if (!token) {
      return Promise.resolve<PagedResponse<SellerOnboardingRequest>>({
        items: [],
        total: 0,
        page: 1,
        page_size: PAGE_SIZE,
      });
    }
    return adminListOnboardingRequests(
      { status, q: debouncedQuery.trim(), page, pageSize: PAGE_SIZE },
      token,
    );
  }, [token, status, debouncedQuery, page]);

  const { data, loading: fetching, refetch } = usePagedList<
    PagedResponse<SellerOnboardingRequest>
  >(fetcher, { token: Boolean(token), status, debouncedQuery, page });

  const rows = useMemo(() => data?.items ?? [], [data]);
  const total = data?.total ?? 0;

  const statusLabel = useCallback(
    (s: OnboardingRequestStatus) =>
      t(
        `status${s.charAt(0).toUpperCase()}${s.slice(1)}` as
          | "statusNew"
          | "statusContacted"
          | "statusOnboarded"
          | "statusDismissed",
      ),
    [t],
  );

  async function setRowStatus(id: number, next: OnboardingRequestStatus) {
    if (!token) return;
    setUpdatingId(id);
    try {
      await adminUpdateOnboardingStatus(id, next, token);
      refetch();
    } finally {
      setUpdatingId(null);
    }
  }

  const actionFor: Record<
    OnboardingRequestStatus,
    { next: OnboardingRequestStatus; label: string } | null
  > = {
    new: { next: "contacted", label: t("markContacted") },
    contacted: { next: "onboarded", label: t("markOnboarded") },
    onboarded: null,
    dismissed: null,
  };

  const columns: Column<SellerOnboardingRequest>[] = [
    {
      key: "store_name",
      label: t("colStore"),
      render: (row) => <strong>{row.store_name}</strong>,
    },
    {
      key: "contact",
      label: t("colContact"),
      render: (row) => (
        <div className={styles.contactCell}>
          <span>{row.contact_phone}</span>
          <span className={styles.muted}>{row.contact_email}</span>
        </div>
      ),
    },
    {
      key: "area",
      label: t("colArea"),
      render: (row) => row.area_label ?? "—",
    },
    {
      key: "source",
      label: t("colSource"),
      render: (row) => row.source ?? "—",
    },
    {
      key: "status",
      label: t("colStatus"),
      render: (row) => (
        <span className={styles.statusBadge}>{statusLabel(row.status)}</span>
      ),
    },
    {
      key: "created_at",
      label: t("colSubmitted"),
      render: (row) => new Date(row.created_at).toLocaleDateString(),
    },
    {
      key: "actions",
      label: t("colActions"),
      render: (row) => {
        const primary = actionFor[row.status];
        return (
          <div className={styles.actions}>
            {primary && (
              <button
                type="button"
                className="btn btn-secondary"
                disabled={updatingId === row.id}
                onClick={() => setRowStatus(row.id, primary.next)}
              >
                {primary.label}
              </button>
            )}
            {row.status !== "dismissed" && (
              <button
                type="button"
                className={styles.dismissBtn}
                disabled={updatingId === row.id}
                onClick={() => setRowStatus(row.id, "dismissed")}
              >
                {t("markDismissed")}
              </button>
            )}
          </div>
        );
      },
    },
  ];

  if (authLoading) {
    return (
      <div
        style={{
          padding: "2rem",
          textAlign: "center",
          color: "var(--color-neutral-500)",
        }}
      >
        {tc("loading")}
      </div>
    );
  }

  return (
    <>
      <div className={styles.toolbar}>
        <div className={styles.filters}>
          <select
            className={styles.select}
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
            aria-label={t("colStatus")}
          >
            <option value="all">{t("filterAll")}</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {statusLabel(s)}
              </option>
            ))}
          </select>
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
      </div>

      {fetching && (
        <div style={{ padding: "1rem", color: "var(--color-neutral-500)" }}>
          {tc("loading")}
        </div>
      )}

      <DataTable
        columns={columns}
        data={rows}
        keyField="id"
        emptyMessage={t("empty")}
        mobileCardRender={(row) => (
          <>
            <div className={mobileStyles.cardTopRow}>
              <span className={mobileStyles.cardTitle}>{row.store_name}</span>
              <span className={styles.statusBadge}>{statusLabel(row.status)}</span>
            </div>
            <div className={styles.contactCell}>
              <span>{row.contact_phone}</span>
              <span className={styles.muted}>{row.contact_email}</span>
            </div>
            <div className={mobileStyles.cardMeta}>
              {(row.area_label ?? "—") + " · " + (row.source ?? "—")}
            </div>
            <div className={styles.actions}>
              {actionFor[row.status] && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={updatingId === row.id}
                  onClick={() =>
                    setRowStatus(row.id, actionFor[row.status]!.next)
                  }
                >
                  {actionFor[row.status]!.label}
                </button>
              )}
              {row.status !== "dismissed" && (
                <button
                  type="button"
                  className={styles.dismissBtn}
                  disabled={updatingId === row.id}
                  onClick={() => setRowStatus(row.id, "dismissed")}
                >
                  {t("markDismissed")}
                </button>
              )}
            </div>
          </>
        )}
      />
      <Pager page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} />
    </>
  );
}
