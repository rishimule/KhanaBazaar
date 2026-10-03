"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import DataTable, { type Column } from "@/components/DataTable";
import LoadError from "@/components/LoadError";
import Pager from "@/components/Pager";
import OrderStatusBadge from "@/components/orders/OrderStatusBadge";
import PaymentStatusPill from "@/components/orders/PaymentStatusPill";
import OrderTotal from "@/components/orders/OrderTotal";
import { listOrdersPaged } from "@/lib/orders";
import { usePagedList } from "@/lib/usePagedList";
import { useVisibilityRefresh } from "@/lib/useVisibilityRefresh";
import { useDebouncedValue } from "@/lib/useDebouncedValue";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import type { Order, OrderListResponse, Service } from "@/types";
import styles from "./page.module.css";

type StatusFilter =
  | "all"
  | "active"
  | "delivered"
  | "cancelled"
  | "needs_quote"
  | "check_payment"
  | "refunds_due";
type SortKey = "date_desc" | "date_asc" | "total_desc" | "total_asc";
const PAGE_SIZE = 20;

export default function SellerOrdersPage() {
  const t = useTranslations("Seller.orders");
  const tc = useTranslations("Seller.common");
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

  // Any filter change resets to page 1 (handled in the control handlers below).
  const fetcher = useCallback(() => {
    if (!token) {
      return Promise.resolve<OrderListResponse>({
        orders: [],
        total: 0,
        page: 1,
        page_size: PAGE_SIZE,
      });
    }
    return listOrdersPaged(token, {
      // The three courier chips are stage filters, not statuses (A1 Task 15).
      status:
        statusFilter === "needs_quote" || statusFilter === "check_payment" || statusFilter === "refunds_due"
          ? "all"
          : statusFilter,
      needs:
        statusFilter === "needs_quote"
          ? "quote"
          : statusFilter === "check_payment"
            ? "payment_check"
            : statusFilter === "refunds_due"
              ? "refund"
              : undefined,
      service_id: serviceId,
      q: debouncedQuery,
      from_date: fromDate,
      to_date: toDate,
      sort: sortKey,
      page,
      page_size: PAGE_SIZE,
    });
  }, [token, statusFilter, serviceId, debouncedQuery, fromDate, toDate, sortKey, page]);

  // `error` was previously dropped here, so a failed fetch rendered the
  // "No orders match these filters." empty state — a seller on patchy mobile
  // data concluded business was quiet and walked away from real orders.
  const { data, loading, error, refetch } = usePagedList<OrderListResponse>(fetcher, {
    token: Boolean(token),
    statusFilter,
    serviceId,
    debouncedQuery,
    fromDate,
    toDate,
    sortKey,
    page,
  });

  // A seller who gets a new-order chime and tabs back must not see a stale
  // list. Quiet: refresh in place rather than replacing the table with a
  // spinner on every window focus.
  useVisibilityRefresh(() => refetch({ quiet: true }));

  const orders = data?.orders ?? [];
  const total = data?.total ?? 0;

  const columns: Column<Order>[] = [
    {
      key: "id",
      label: t("col.order"),
      render: (o) => <span className={styles.mono}>#{o.id}</span>,
    },
    {
      key: "placed_at",
      label: t("col.placed"),
      render: (o) => (
        <time title={o.placed_at} suppressHydrationWarning>
          {new Date(o.placed_at).toLocaleString()}
        </time>
      ),
    },
    {
      key: "customer_name",
      label: t("col.customer"),
      render: (o) => o.customer_name ?? "—",
    },
    {
      key: "service_name",
      label: t("col.service"),
      render: (o) => <span className={styles.serviceChip}>{o.service_name}</span>,
    },
    {
      key: "items",
      label: t("col.items"),
      render: (o) => `${o.items.length}`,
    },
    {
      key: "total",
      label: t("col.total"),
      render: (o) => <OrderTotal order={o} className={styles.right} />,
    },
    {
      key: "payment",
      label: t("col.payment"),
      render: (o) => (
        <>
          <PaymentStatusPill
            payment={o.payment}
            refundDue={o.courier?.refund_due}
            courier={o.delivery_mode === "courier"}
          />
          {/* Only while it is an open question: the claim timestamp outlives
              the payment, and cancelling a courier order already answered it
              (refund due, or reported as not received). */}
          {o.payment.customer_claimed_at &&
            o.payment.status === "pending" &&
            !(o.delivery_mode === "courier" && o.status === "cancelled") && (
              <span className={styles.claimBadge}>{t("customerSaysPaid")}</span>
            )}
        </>
      ),
    },
    {
      key: "status",
      label: t("col.status"),
      render: (o) => (
        <>
          <OrderStatusBadge status={o.status} deliveryMode={o.delivery_mode} />
          {o.delivery_mode === "courier" && (
            <span className={styles.claimBadge}>{t("courierTag")}</span>
          )}
        </>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>{t("title")}</h1>

      <div className={styles.controls}>
        <div className={styles.chips} role="tablist">
          {(
            [
              "all",
              "active",
              "needs_quote",
              "check_payment",
              "refunds_due",
              "delivered",
              "cancelled",
            ] as StatusFilter[]
          ).map((s) => (
            <button
              key={s}
              type="button"
              className={statusFilter === s ? styles.chipActive : styles.chip}
              onClick={() => {
                setStatusFilter(s);
                // Oldest debts first (by order date: cancellation time isn't sortable).
                if (s === "refunds_due") setSortKey("date_asc");
                setPage(1);
              }}
            >
              {t(`filter.${s}`)}
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
          <option value="date_desc">{t("sort.dateDesc")}</option>
          <option value="date_asc">{t("sort.dateAsc")}</option>
          <option value="total_desc">{t("sort.totalDesc")}</option>
          <option value="total_asc">{t("sort.totalAsc")}</option>
        </select>
      </div>

      {loading ? (
        <div className={styles.empty}>{tc("loading")}</div>
      ) : error && orders.length === 0 ? (
        <LoadError
          variant="card"
          error={error}
          title={t("loadFailedTitle")}
          body={t("loadFailedBody")}
          onRetry={() => refetch()}
        />
      ) : (
        <>
          {error && (
            <LoadError
              variant="banner"
              error={error}
              title={t("loadFailedTitle")}
              onRetry={() => refetch()}
            />
          )}
          <div
            className={styles.rowClickable}
            onClick={(e) => {
              const tr = (e.target as HTMLElement).closest("tr[data-order-id]");
              if (tr) {
                const id = tr.getAttribute("data-order-id");
                if (id) router.push(`/seller/orders/${id}`);
              }
            }}
          >
            <DataTable
              columns={columns}
              data={orders}
              keyField="id"
              emptyMessage={t("emptyMessage")}
              mobileCardRender={(o) => (
                <a href={`/seller/orders/${o.id}`} className={styles.mobileLink}>
                  <div className={styles.mobileTop}>
                    <span className={styles.mono}>#{o.id}</span>
                    <span>
                      <OrderStatusBadge status={o.status} deliveryMode={o.delivery_mode} />
                      {o.delivery_mode === "courier" && (
                        <span className={styles.claimBadge}>{t("courierTag")}</span>
                      )}
                    </span>
                  </div>
                  <div>
                    {o.customer_name ?? "—"} · {o.service_name}
                  </div>
                  <div className={styles.mobileBot}>
                    <OrderTotal order={o} />
                    <PaymentStatusPill
                      payment={o.payment}
                      refundDue={o.courier?.refund_due}
                      courier={o.delivery_mode === "courier"}
                    />
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
