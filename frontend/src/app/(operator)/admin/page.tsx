"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import type { AdminMetrics } from "@/types";
import StatsCard from "@/components/StatsCard";
import DashboardHeader from "@/components/admin/DashboardHeader";
import AttentionBanner from "@/components/admin/AttentionBanner";
import GmvChart from "@/components/admin/GmvChart";
import ApplicationPipeline from "@/components/admin/ApplicationPipeline";
import OrdersByService from "@/components/admin/OrdersByService";
import RecentOrders from "@/components/admin/RecentOrders";
import QuickActions from "@/components/admin/QuickActions";
import styles from "./page.module.css";

const EMPTY: AdminMetrics = {
  active_orders: 0,
  orders_today: 0,
  orders_this_month: 0,
  gmv_this_month: 0,
  gmv_last_month: 0,
  gmv_trend_pct: 0,
  active_master_products: 0,
  active_categories: 0,
  active_stores: 0,
  pending_applications: 0,
  approved_sellers: 0,
  rejected_sellers: 0,
  open_change_requests: 0,
  orders_by_service: [],
};

export default function AdminDashboardPage() {
  const t = useTranslations("Admin.dashboard");
  const tc = useTranslations("Admin.common");
  const router = useRouter();
  const { dbUser, token, loading } = useAuth();
  const [metrics, setMetrics] = useState<AdminMetrics | null>(null);
  const [fetching, setFetching] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(
    (refresh = false) => {
      if (!token) return;
      if (refresh) setRefreshing(true);
      get<AdminMetrics>("/api/v1/admin/metrics", token)
        .then(setMetrics)
        .catch(() => {})
        .finally(() => {
          setFetching(false);
          setRefreshing(false);
        });
    },
    [token]
  );

  useEffect(() => {
    if (!loading && (!dbUser || dbUser.role !== "admin")) {
      router.push(dbUser ? "/" : "/login");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial metrics fetch sets state in async callbacks
    if (!loading && dbUser && token) load();
  }, [loading, dbUser, token, router, load]);

  if (loading || fetching) {
    return (
      <div style={{ padding: "2rem", textAlign: "center", color: "var(--color-neutral-500)" }}>
        {tc("loading")}
      </div>
    );
  }

  const m = metrics ?? EMPTY;
  const reviewQueue = m.pending_applications + m.open_change_requests;

  return (
    <div className={styles.page}>
      <DashboardHeader
        reviewQueue={reviewQueue}
        onRefresh={() => load(true)}
        refreshing={refreshing}
      />

      <AttentionBanner
        pendingApplications={m.pending_applications}
        openChangeRequests={m.open_change_requests}
      />

      <div className={styles.statsGrid}>
        <StatsCard
          icon="💰"
          label={t("gmvThisMonth")}
          value={`₹${m.gmv_this_month.toFixed(0)}`}
          variant="accent"
          trend={
            m.gmv_trend_pct !== 0
              ? t("gmvCardTrend", {
                  pct: Math.abs(m.gmv_trend_pct),
                  last: m.gmv_last_month.toFixed(0),
                })
              : undefined
          }
          trendDirection={m.gmv_trend_pct >= 0 ? "up" : "down"}
        />
        <StatsCard
          icon="🛒"
          label={t("activeOrders")}
          value={m.active_orders}
          variant={m.active_orders > 0 ? "primary" : "info"}
          trend={m.active_orders > 0 ? t("activeOrdersSub") : undefined}
          trendDirection="up"
        />
        <StatsCard
          icon="📈"
          label={t("ordersThisMonth")}
          value={m.orders_this_month}
          variant="info"
          trend={t("ordersThisMonthSub", { count: m.orders_today })}
          trendDirection="up"
        />
        <StatsCard
          icon="🏪"
          label={t("activeStores")}
          value={m.active_stores}
          variant="primary"
          trend={t("activeStoresSub", { count: m.approved_sellers })}
          trendDirection="up"
        />
        <StatsCard icon="🗓️" label={t("ordersToday")} value={m.orders_today} variant="info" />
        <StatsCard
          icon="🤝"
          label={t("approvedSellers")}
          value={m.approved_sellers}
          variant="primary"
        />
        <StatsCard
          icon="📦"
          label={t("masterProducts")}
          value={m.active_master_products}
          variant="accent"
        />
        <StatsCard icon="🏷️" label={t("categories")} value={m.active_categories} variant="info" />
      </div>

      <div className={styles.grid}>
        <div className={styles.main}>
          <GmvChart />
          <RecentOrders />
        </div>
        <aside className={styles.rail}>
          <ApplicationPipeline
            approved={m.approved_sellers}
            pending={m.pending_applications}
            rejected={m.rejected_sellers}
          />
          <OrdersByService services={m.orders_by_service} />
          <QuickActions />
        </aside>
      </div>
    </div>
  );
}
