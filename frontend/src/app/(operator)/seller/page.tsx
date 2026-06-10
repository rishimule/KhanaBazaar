"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { get, patch } from "@/lib/api";
import type { SellerMetrics } from "@/types";
import StatsCard from "@/components/StatsCard";
import DashboardHeader from "@/components/seller/DashboardHeader";
import CloseStoreModal from "@/components/seller/CloseStoreModal";
import AttentionBanner from "@/components/seller/AttentionBanner";
import RevenueChart from "@/components/seller/RevenueChart";
import OrderStatusDonut from "@/components/seller/OrderStatusDonut";
import InventoryByService from "@/components/seller/InventoryByService";
import RecentOrders from "@/components/seller/RecentOrders";
import QuickActions from "@/components/seller/QuickActions";
import styles from "./page.module.css";

const EMPTY: SellerMetrics = {
  active_orders: 0,
  orders_today: 0,
  orders_this_month: 0,
  revenue_this_month: 0,
  revenue_last_month: 0,
  revenue_trend_pct: 0,
  total_products: 0,
  out_of_stock: 0,
  unavailable: 0,
  store_active: false,
  store_paused: false,
  pin_confirmed: false,
  store_name: "",
  order_status_counts: { delivered: 0, packed: 0, dispatched: 0, pending: 0, cancelled: 0 },
  inventory_by_service: [],
  top_subcategory: null,
};

export default function SellerDashboardPage() {
  const router = useRouter();
  const { dbUser, token, loading } = useAuth();
  const [metrics, setMetrics] = useState<SellerMetrics | null>(null);
  const [fetching, setFetching] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [pauseBusy, setPauseBusy] = useState(false);
  const [closePrompt, setClosePrompt] = useState(false);

  const load = useCallback(
    (refresh = false) => {
      if (!token) return;
      if (refresh) setRefreshing(true);
      get<SellerMetrics>("/api/v1/sellers/me/metrics", token)
        .then(setMetrics)
        .catch(() => {})
        .finally(() => {
          setFetching(false);
          setRefreshing(false);
        });
    },
    [token]
  );

  const togglePause = useCallback(
    async (body: { is_paused: boolean; reason?: string; paused_until?: string }) => {
      if (!token) return;
      setPauseBusy(true);
      try {
        await patch("/api/v1/sellers/me/store/pause", body, token);
        setClosePrompt(false);
        load(true);
      } catch {
        // surfaced via metrics not flipping; keep dashboard responsive
      } finally {
        setPauseBusy(false);
      }
    },
    [token, load]
  );

  // Closing opens a modal (optional reason + reopen date); reopening is a
  // direct toggle that also clears any prior reason/date server-side.
  const handlePauseToggle = useCallback(() => {
    if (metrics?.store_paused) {
      togglePause({ is_paused: false });
    } else {
      setClosePrompt(true);
    }
  }, [metrics?.store_paused, togglePause]);

  useEffect(() => {
    if (!loading && (!dbUser || dbUser.role !== "seller")) {
      router.push(dbUser ? "/" : "/login");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial metrics fetch sets state in async callbacks
    if (!loading && dbUser && token) load();
  }, [loading, dbUser, token, router, load]);

  if (loading || fetching) {
    return (
      <div style={{ padding: "2rem", textAlign: "center", color: "var(--color-neutral-500)" }}>
        Loading…
      </div>
    );
  }

  const m = metrics ?? EMPTY;

  return (
    <div className={styles.page}>
      <DashboardHeader
        fullName={dbUser?.full_name}
        storeName={m.store_name}
        storePaused={m.store_paused}
        onRefresh={() => load(true)}
        refreshing={refreshing}
        onTogglePause={handlePauseToggle}
        pauseBusy={pauseBusy}
        avatarUrl={dbUser?.avatar_url}
      />

      {closePrompt && (
        <CloseStoreModal
          busy={pauseBusy}
          onConfirm={({ reason, paused_until }) =>
            togglePause({ is_paused: true, reason, paused_until })
          }
          onClose={() => setClosePrompt(false)}
        />
      )}

      <AttentionBanner activeOrders={m.active_orders} counts={m.order_status_counts} />

      <div className={styles.statsGrid}>
        <StatsCard
          icon="💰"
          label="Revenue · this month"
          value={`₹${m.revenue_this_month.toFixed(0)}`}
          variant="accent"
          trend={
            m.revenue_trend_pct !== 0
              ? `${Math.abs(m.revenue_trend_pct)}% vs ₹${m.revenue_last_month.toFixed(0)} last month`
              : undefined
          }
          trendDirection={m.revenue_trend_pct >= 0 ? "up" : "down"}
        />
        <StatsCard
          icon="🛒"
          label="Active orders"
          value={m.active_orders}
          variant={m.active_orders > 0 ? "primary" : "info"}
          trend={m.active_orders > 0 ? "Needs attention" : undefined}
          trendDirection="up"
        />
        <StatsCard icon="🗓️" label="Orders today" value={m.orders_today} variant="info" />
        <StatsCard icon="📦" label="Total products" value={m.total_products} variant="primary" />
      </div>

      <div className={styles.grid}>
        <div className={styles.main}>
          <RevenueChart />
          <RecentOrders />
        </div>
        <aside className={styles.rail}>
          <OrderStatusDonut counts={m.order_status_counts} />
          <InventoryByService
            services={m.inventory_by_service}
            outOfStock={m.out_of_stock}
            topSubcategory={m.top_subcategory}
          />
          <QuickActions />
        </aside>
      </div>
    </div>
  );
}
