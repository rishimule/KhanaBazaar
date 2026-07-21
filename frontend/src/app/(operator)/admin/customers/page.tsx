"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
//
// Customer supervisor list with drill-down to the per-customer hub
// (Overview / Activity / Orders / Addresses / Notifications).

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import DataTable, { Column } from "@/components/DataTable";
import Pager from "@/components/Pager";
import CustomerStatusPill from "@/components/admin/CustomerStatusPill";
import { usePagedList } from "@/lib/usePagedList";
import { useDebouncedValue } from "@/lib/useDebouncedValue";
import { useAuth } from "@/lib/AuthContext";
import { fetchCustomerList } from "@/lib/adminCustomers";
import type {
  AdminCustomerListItem,
  AdminCustomerListResponse,
  CustomerAccountStatus,
} from "@/types";
import styles from "./page.module.css";
import mobileStyles from "@/components/DataTableCard.module.css";

const PAGE_SIZE = 20;

type StatusFilter = "" | CustomerAccountStatus;

const FILTERS: StatusFilter[] = [
  "",
  "active",
  "deactivated",
  "suspended",
  "deleted",
];

function joinedDate(iso: string): string {
  return new Date(iso).toLocaleDateString();
}

export default function AdminCustomersListPage() {
  const t = useTranslations("Admin.customers");
  const tc = useTranslations("Admin.common");
  const { token } = useAuth();

  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("");
  const [page, setPage] = useState(1);
  const debouncedQuery = useDebouncedValue(query, 300);

  const fetcher = useCallback(() => {
    if (!token) {
      return Promise.resolve<AdminCustomerListResponse>({ items: [], total: 0 });
    }
    return fetchCustomerList(token, {
      q: debouncedQuery,
      status,
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
    });
  }, [token, debouncedQuery, status, page]);

  const { data, loading: fetching } = usePagedList<AdminCustomerListResponse>(
    fetcher,
    { token: Boolean(token), debouncedQuery, status, page },
  );
  const customers = useMemo(() => data?.items ?? [], [data]);
  const total = data?.total ?? 0;

  const columns: Column<AdminCustomerListItem>[] = [
    {
      key: "customer",
      label: t("col.customer"),
      render: (row) => (
        <div className={styles.ownerCell}>
          <strong>{row.full_name || t("noName")}</strong>
          <span className={styles.ownerEmail}>{row.email}</span>
        </div>
      ),
    },
    {
      key: "phone",
      label: t("col.phone"),
      render: (row) => row.phone ?? "—",
    },
    {
      key: "status",
      label: t("col.status"),
      render: (row) => <CustomerStatusPill status={row.account_status} />,
    },
    {
      key: "joined",
      label: t("col.joined"),
      render: (row) => joinedDate(row.created_at),
    },
    {
      key: "actions",
      label: t("col.actions"),
      render: (row) => (
        <Link
          href={`/admin/customers/${row.customer_profile_id}`}
          className={styles.reviewBtn}
        >
          {t("manage")}
        </Link>
      ),
    },
  ];

  return (
    <>
      <div className={styles.toolbar}>
        <div className={styles.filters}>
          {FILTERS.map((f) => (
            <button
              key={f || "all"}
              type="button"
              className={f === status ? styles.tabActive : styles.tab}
              onClick={() => {
                setStatus(f);
                setPage(1);
              }}
            >
              {t(`filter.${f || "all"}`)}
            </button>
          ))}
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
        data={customers}
        keyField="customer_profile_id"
        emptyMessage={t("empty")}
        mobileCardRender={(row) => (
          <>
            <div className={mobileStyles.cardTopRow}>
              <span className={mobileStyles.cardTitle}>
                {row.full_name || t("noName")}
              </span>
              <CustomerStatusPill status={row.account_status} />
            </div>
            <div className={styles.ownerCell}>
              <span className={styles.ownerEmail}>{row.email}</span>
              {row.phone && (
                <span className={styles.ownerEmail}>{row.phone}</span>
              )}
            </div>
            <div className={mobileStyles.cardMeta}>
              {t("cardMeta", { ago: joinedDate(row.created_at) })}
            </div>
            <Link
              href={`/admin/customers/${row.customer_profile_id}`}
              className={styles.reviewBtn}
              style={{
                width: "100%",
                minHeight: 44,
                justifyContent: "center",
              }}
            >
              {t("manage")}
            </Link>
          </>
        )}
      />
      <Pager
        page={page}
        pageSize={PAGE_SIZE}
        total={total}
        onPage={setPage}
        labels={{
          prev: t("prev"),
          next: t("next"),
          summary: (from, to, n) => t("showing", { from, to, total: n }),
        }}
      />
    </>
  );
}
