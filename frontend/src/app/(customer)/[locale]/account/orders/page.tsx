"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import DataTable, { type Column } from "@/components/DataTable";
import OrderStatusBadge from "@/components/orders/OrderStatusBadge";
import PaymentStatusPill from "@/components/orders/PaymentStatusPill";
import { listOrders } from "@/lib/orders";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import type { Order, OrderStatus, Service } from "@/types";
import styles from "./page.module.css";

const ACTIVE: OrderStatus[] = ["pending", "packed", "dispatched"];
type StatusFilter = "all" | "active" | "delivered" | "cancelled";
type SortKey = "date_desc" | "date_asc" | "total_desc" | "total_asc";
const PAGE_SIZE = 20;

export default function CustomerOrdersPage() {
  const { token } = useAuth();
  const t = useTranslations("Account.orders");
  const router = useRouter();

  const [allOrders, setAllOrders] = useState<Order[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [serviceId, setServiceId] = useState<string>("");
  const [fromDate, setFromDate] = useState<string>("");
  const [toDate, setToDate] = useState<string>("");
  const [query, setQuery] = useState<string>("");
  const [sortKey, setSortKey] = useState<SortKey>("date_desc");
  const [pageCount, setPageCount] = useState(1);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    Promise.all([
      listOrders(token),
      get<Service[]>("/api/v1/catalog/services").catch(() => [] as Service[]),
    ])
      .then(([orders, svcs]) => {
        if (cancelled) return;
        setAllOrders(orders);
        setServices(svcs);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const filtered = useMemo(() => {
    let out = allOrders.slice();
    if (statusFilter === "active") out = out.filter((o) => ACTIVE.includes(o.status));
    else if (statusFilter === "delivered")
      out = out.filter((o) => o.status === "delivered");
    else if (statusFilter === "cancelled")
      out = out.filter((o) => o.status === "cancelled");
    if (serviceId) out = out.filter((o) => String(o.service_id) === serviceId);
    if (fromDate) out = out.filter((o) => o.placed_at >= fromDate);
    if (toDate) out = out.filter((o) => o.placed_at <= `${toDate}T23:59:59Z`);
    if (query.trim()) {
      const q = query.trim().toLowerCase().replace(/^#/, "");
      out = out.filter(
        (o) =>
          String(o.id).includes(q) ||
          o.store_name.toLowerCase().includes(q),
      );
    }
    out.sort((a, b) => {
      switch (sortKey) {
        case "date_asc":
          return a.placed_at.localeCompare(b.placed_at);
        case "total_asc":
          return a.total - b.total;
        case "total_desc":
          return b.total - a.total;
        case "date_desc":
        default:
          return b.placed_at.localeCompare(a.placed_at);
      }
    });
    return out;
  }, [allOrders, statusFilter, serviceId, fromDate, toDate, query, sortKey]);

  const visible = filtered.slice(0, pageCount * PAGE_SIZE);

  const columns: Column<Order>[] = [
    {
      key: "id",
      label: t("colOrderId"),
      render: (o) => <span className={styles.mono}>#{o.id}</span>,
    },
    {
      key: "placed_at",
      label: t("colDate"),
      render: (o) => (
        <time title={o.placed_at} suppressHydrationWarning>
          {new Date(o.placed_at).toLocaleString()}
        </time>
      ),
    },
    { key: "store_name", label: t("colStore") },
    {
      key: "service_name",
      label: t("colService"),
      render: (o) => <span className={styles.serviceChip}>{o.service_name}</span>,
    },
    {
      key: "items",
      label: t("colItems"),
      render: (o) => t("itemCount", { count: o.items.length }),
    },
    {
      key: "total",
      label: t("colTotal"),
      render: (o) => <span className={styles.right}>₹{o.total.toFixed(2)}</span>,
    },
    {
      key: "payment",
      label: t("colPayment"),
      render: (o) => <PaymentStatusPill payment={o.payment} />,
    },
    {
      key: "status",
      label: t("colStatus"),
      render: (o) => <OrderStatusBadge status={o.status} />,
    },
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
                setPageCount(1);
              }}
            >
              {t(`chip.${s}`)}
            </button>
          ))}
        </div>
        <select
          className={styles.select}
          value={serviceId}
          onChange={(e) => {
            setServiceId(e.target.value);
            setPageCount(1);
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
          onChange={(e) => setFromDate(e.target.value)}
          aria-label={t("fromDate")}
        />
        <input
          type="date"
          className={styles.dateInput}
          value={toDate}
          onChange={(e) => setToDate(e.target.value)}
          aria-label={t("toDate")}
        />
        <input
          type="search"
          className={styles.search}
          placeholder={t("searchPlaceholder")}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPageCount(1);
          }}
        />
        <select
          className={styles.select}
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}
        >
          <option value="date_desc">{t("sort.dateDesc")}</option>
          <option value="date_asc">{t("sort.dateAsc")}</option>
          <option value="total_desc">{t("sort.totalDesc")}</option>
          <option value="total_asc">{t("sort.totalAsc")}</option>
        </select>
      </div>

      {loading ? (
        <div className={styles.empty}>{t("loading")}</div>
      ) : (
        <>
          <div
            className={styles.rowClickable}
            onClick={(e) => {
              const tr = (e.target as HTMLElement).closest(
                "tr[data-order-id]",
              );
              if (tr) {
                const id = tr.getAttribute("data-order-id");
                if (id) router.push(`/account/orders/${id}`);
              }
            }}
          >
            <DataTable
              columns={columns}
              data={visible}
              keyField="id"
              emptyMessage={t("emptyHistory")}
              mobileCardRender={(o) => (
                <a href={`/account/orders/${o.id}`} className={styles.mobileLink}>
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
          {visible.length < filtered.length && (
            <button
              type="button"
              className={`btn btn-outline ${styles.loadMore}`}
              onClick={() => setPageCount((p) => p + 1)}
            >
              {t("loadMore")}
            </button>
          )}
        </>
      )}
    </div>
  );
}
