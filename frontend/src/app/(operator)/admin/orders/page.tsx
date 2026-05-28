"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import DataTable, { type Column } from "@/components/DataTable";
import Pager from "@/components/Pager";
import OrderStatusBadge from "@/components/orders/OrderStatusBadge";
import PaymentStatusPill from "@/components/orders/PaymentStatusPill";
import { listAdminOrders } from "@/lib/orders";
import { usePagedList } from "@/lib/usePagedList";
import { useDebouncedValue } from "@/lib/useDebouncedValue";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import type { Order, OrderListResponse, Service } from "@/types";
import styles from "./page.module.css";

type StatusFilter = "all" | "active" | "delivered" | "cancelled";
type SortKey = "date_desc" | "date_asc" | "total_desc" | "total_asc";
const PAGE_SIZE = 20;

const STATUS_FILTER_KEYS: Record<StatusFilter, string> = {
  all: "filterAll",
  active: "filterActive",
  delivered: "filterDelivered",
  cancelled: "filterCancelled",
};

export default function AdminOrdersPage() {
  const t = useTranslations("Admin.orders");
  const tc = useTranslations("Admin.common");
  const { token } = useAuth();
  const router = useRouter();

  const [services, setServices] = useState<Service[]>([]);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [serviceId, setServiceId] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("date_desc");
  const [page, setPage] = useState(1);
  const debouncedQuery = useDebouncedValue(query, 300);

  useEffect(() => {
    get<Service[]>("/api/v1/catalog/services")
      .then(setServices)
      .catch(() => setServices([]));
  }, []);

  // Any filter change resets to page 1 (done in the control handlers below).
  const fetcher = useCallback(() => {
    if (!token) {
      return Promise.resolve<OrderListResponse>({
        orders: [],
        total: 0,
        page: 1,
        page_size: PAGE_SIZE,
      });
    }
    return listAdminOrders(token, {
      status: statusFilter,
      service_id: serviceId,
      q: debouncedQuery,
      from_date: fromDate,
      to_date: toDate,
      sort: sortKey,
      page,
      page_size: PAGE_SIZE,
    });
  }, [token, statusFilter, serviceId, debouncedQuery, fromDate, toDate, sortKey, page]);

  const { data, loading } = usePagedList<OrderListResponse>(fetcher, {
    token: Boolean(token),
    statusFilter,
    serviceId,
    debouncedQuery,
    fromDate,
    toDate,
    sortKey,
    page,
  });

  const orders = data?.orders ?? [];
  const total = data?.total ?? 0;

  const columns: Column<Order>[] = [
    {
      key: "id",
      label: t("colOrder"),
      render: (o) => <span className={styles.mono}>#{o.id}</span>,
    },
    {
      key: "placed_at",
      label: t("colPlaced"),
      render: (o) => (
        <time title={o.placed_at} suppressHydrationWarning>
          {new Date(o.placed_at).toLocaleString()}
        </time>
      ),
    },
    { key: "store_name", label: t("colStore") },
    { key: "customer_name", label: t("colCustomer"), render: (o) => o.customer_name ?? "—" },
    {
      key: "service_name",
      label: t("colService"),
      render: (o) => <span className={styles.serviceChip}>{o.service_name}</span>,
    },
    { key: "items", label: t("colItems"), render: (o) => `${o.items.length}` },
    {
      key: "total",
      label: t("colTotal"),
      render: (o) => <span className={styles.right}>₹{o.total.toFixed(2)}</span>,
    },
    { key: "payment", label: t("colPayment"), render: (o) => <PaymentStatusPill payment={o.payment} /> },
    { key: "status", label: t("colStatus"), render: (o) => <OrderStatusBadge status={o.status} /> },
  ];

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>{t("title")}</h1>

      <div className={styles.controls}>
        <div className={styles.chips} role="tablist">
          {(["all", "active", "delivered", "cancelled"] as StatusFilter[]).map((s) => (
            <button
              key={s}
              type="button"
              className={statusFilter === s ? styles.chipActive : styles.chip}
              onClick={() => {
                setStatusFilter(s);
                setPage(1);
              }}
            >
              {t(STATUS_FILTER_KEYS[s])}
            </button>
          ))}
        </div>
        <select
          className={styles.select}
          value={serviceId}
          onChange={(e) => {
            setServiceId(e.target.value);
            setPage(1);
          }}
        >
          <option value="">{t("allServices")}</option>
          {services.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <input
          type="date"
          className={styles.dateInput}
          value={fromDate}
          onChange={(e) => {
            setFromDate(e.target.value);
            setPage(1);
          }}
          aria-label={t("fromDate")}
        />
        <input
          type="date"
          className={styles.dateInput}
          value={toDate}
          onChange={(e) => {
            setToDate(e.target.value);
            setPage(1);
          }}
          aria-label={t("toDate")}
        />
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
        <select
          className={styles.select}
          value={sortKey}
          onChange={(e) => {
            setSortKey(e.target.value as SortKey);
            setPage(1);
          }}
        >
          <option value="date_desc">{t("sortNewest")}</option>
          <option value="date_asc">{t("sortOldest")}</option>
          <option value="total_desc">{t("sortTotalDesc")}</option>
          <option value="total_asc">{t("sortTotalAsc")}</option>
        </select>
      </div>

      {loading ? (
        <div className={styles.empty}>{tc("loading")}</div>
      ) : (
        <>
          <div
            className={styles.rowClickable}
            onClick={(e) => {
              const tr = (e.target as HTMLElement).closest("tr[data-order-id]");
              if (tr) {
                const id = tr.getAttribute("data-order-id");
                if (id) router.push(`/admin/orders/${id}`);
              }
            }}
          >
            <DataTable
              columns={columns}
              data={orders}
              keyField="id"
              emptyMessage={t("emptyMessage")}
              mobileCardRender={(o) => (
                <a href={`/admin/orders/${o.id}`} className={styles.mobileLink}>
                  <div className={styles.mobileTop}>
                    <span className={styles.mono}>#{o.id}</span>
                    <OrderStatusBadge status={o.status} />
                  </div>
                  <div>
                    {o.store_name} · {o.service_name}
                  </div>
                  <div className={styles.mobileBot}>
                    <span>₹{o.total.toFixed(2)}</span>
                    <PaymentStatusPill payment={o.payment} />
                  </div>
                </a>
              )}
            />
          </div>
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
      )}
    </div>
  );
}
