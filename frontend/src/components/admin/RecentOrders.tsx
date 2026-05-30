"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import type { OrderListResponse } from "@/types";
import OrderStatusBadge from "@/components/orders/OrderStatusBadge";
import PaymentStatusPill from "@/components/orders/PaymentStatusPill";
import styles from "./RecentOrders.module.css";

type Tab = "all" | "active" | "delivered" | "cancelled";
const TABS: Tab[] = ["all", "active", "delivered", "cancelled"];
const TAB_KEY: Record<Tab, "tabAll" | "tabActive" | "tabDelivered" | "tabCancelled"> = {
  all: "tabAll",
  active: "tabActive",
  delivered: "tabDelivered",
  cancelled: "tabCancelled",
};

const PAGE_SIZE = 5;

function sevenDaysAgoIsoDate(): string {
  const d = new Date();
  d.setDate(d.getDate() - 6);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function initials(name?: string | null): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  return (parts[0]?.[0] ?? "").concat(parts[1]?.[0] ?? "").toUpperCase() || "?";
}

function shortTime(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function RecentOrders() {
  const t = useTranslations("Admin.dashboard");
  const tc = useTranslations("Admin.common");
  const { token } = useAuth();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("all");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<OrderListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    const params = new URLSearchParams({
      from_date: sevenDaysAgoIsoDate(),
      sort: "date_desc",
      page: String(page),
      page_size: String(PAGE_SIZE),
    });
    if (tab !== "all") params.set("status", tab);
    get<OrderListResponse>(`/api/v1/orders?${params.toString()}`, token)
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setError(false);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, tab, page]);

  function switchTab(next: Tab) {
    setTab(next);
    setPage(1);
  }

  const orders = data?.orders ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <section className={styles.card}>
      <div className={styles.head}>
        <div>
          <h2 className={styles.title}>{t("recentOrders")}</h2>
          <p className={styles.sub}>{t("recentSubtitle")}</p>
        </div>
        <Link href="/admin/orders" className={styles.viewAll}>
          {t("viewAllOrders")} →
        </Link>
      </div>

      <div className={styles.tabs} role="tablist">
        {TABS.map((tb) => (
          <button
            key={tb}
            type="button"
            className={tb === tab ? styles.tabOn : styles.tab}
            onClick={() => switchTab(tb)}
          >
            {t(TAB_KEY[tb])}
          </button>
        ))}
      </div>

      {error ? (
        <div className={styles.empty}>{t("ordersError")}</div>
      ) : loading ? (
        <div className={styles.empty}>{tc("loading")}</div>
      ) : orders.length === 0 ? (
        <div className={styles.empty}>{t("ordersEmpty")}</div>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>{t("colOrder")}</th>
              <th>{t("colStore")}</th>
              <th>{t("colCustomer")}</th>
              <th>{t("colService")}</th>
              <th>{t("colItems")}</th>
              <th>{t("colTotal")}</th>
              <th>{t("colPayment")}</th>
              <th>{t("colStatus")}</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o) => (
              <tr
                key={o.id}
                className={styles.row}
                onClick={() => router.push(`/admin/orders/${o.id}`)}
              >
                <td className={styles.idCell}>#{o.id}</td>
                <td>{o.store_name}</td>
                <td>
                  <div className={styles.customer}>
                    <span className={styles.avatar}>{initials(o.customer_name)}</span>
                    <div className={styles.custInfo}>
                      <span className={styles.custName}>{o.customer_name ?? "—"}</span>
                      <span className={styles.custTime}>{shortTime(o.placed_at)}</span>
                    </div>
                  </div>
                </td>
                <td>
                  <span className={styles.serviceChip}>{o.service_name}</span>
                </td>
                <td>{o.items.length}</td>
                <td className={styles.total}>₹{o.total.toFixed(2)}</td>
                <td>
                  <PaymentStatusPill payment={o.payment} />
                </td>
                <td>
                  <OrderStatusBadge status={o.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {!loading && !error && total > PAGE_SIZE && (
        <div className={styles.pager}>
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className={styles.pagerBtn}
          >
            {t("pagerPrev")}
          </button>
          <span className={styles.pageInfo}>
            {t("pageInfo", { page, total: totalPages })}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            className={styles.pagerBtn}
          >
            {t("pagerNext")}
          </button>
        </div>
      )}
    </section>
  );
}
