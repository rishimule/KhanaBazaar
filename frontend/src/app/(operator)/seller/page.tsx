"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import StatsCard from "@/components/StatsCard";
import styles from "./page.module.css";

interface SellerMetrics {
  active_orders: number;
  orders_today: number;
  orders_this_month: number;
  revenue_this_month: number;
  total_products: number;
  out_of_stock: number;
  unavailable: number;
  store_active: boolean;
  pin_confirmed: boolean;
}

export default function SellerDashboardPage() {
  const router = useRouter();
  const { dbUser, token, loading } = useAuth();
  const [metrics, setMetrics] = useState<SellerMetrics | null>(null);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (!loading && (!dbUser || dbUser.role !== "seller")) {
      router.push(dbUser ? "/" : "/login");
      return;
    }
    if (!loading && dbUser && token) {
      get<SellerMetrics>("/api/v1/sellers/me/metrics", token)
        .then(setMetrics)
        .catch(() => {})
        .finally(() => setFetching(false));
    }
  }, [loading, dbUser, token, router]);

  if (loading || fetching) {
    return (
      <div style={{ padding: "2rem", textAlign: "center", color: "var(--color-neutral-500)" }}>
        Loading…
      </div>
    );
  }

  const m = metrics ?? {
    active_orders: 0,
    orders_today: 0,
    orders_this_month: 0,
    revenue_this_month: 0,
    total_products: 0,
    out_of_stock: 0,
    unavailable: 0,
    store_active: false,
    pin_confirmed: false,
  };

  return (
    <>
      <div className={styles.statsGrid}>
        <StatsCard
          icon="📦"
          label="Active orders"
          value={m.active_orders}
          variant={m.active_orders > 0 ? "primary" : "info"}
          trend={m.active_orders > 0 ? "needs attention" : "no orders waiting"}
          trendDirection={m.active_orders > 0 ? "up" : "down"}
        />
        <StatsCard icon="🗓️" label="Orders today" value={m.orders_today} variant="accent" />
        <StatsCard icon="📈" label="Orders this month" value={m.orders_this_month} variant="info" />
        <StatsCard
          icon="💰"
          label="Revenue (delivered, this month)"
          value={`₹${m.revenue_this_month.toFixed(0)}`}
          variant="accent"
        />
        <StatsCard icon="🏷️" label="Total products" value={m.total_products} variant="primary" />
        <StatsCard
          icon="⚠️"
          label="Out of stock"
          value={m.out_of_stock}
          variant={m.out_of_stock > 0 ? "warning" : "info"}
        />
        <StatsCard
          icon="🚫"
          label="Unavailable"
          value={m.unavailable}
          variant={m.unavailable > 0 ? "warning" : "info"}
        />
        <StatsCard
          icon="🏪"
          label="Store status"
          value={m.store_active ? "Active" : "Inactive"}
          variant={m.store_active ? "accent" : "warning"}
        />
        <StatsCard
          icon="📍"
          label="Pin"
          value={m.pin_confirmed ? "Confirmed" : "Not confirmed"}
          variant={m.pin_confirmed ? "info" : "warning"}
        />
      </div>

      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Quick actions</h2>
        </div>
        <div className={styles.quickActions}>
          <Link href="/seller/orders" className={styles.actionCard}>
            <div className={styles.actionIcon}>📦</div>
            <div className={styles.actionInfo}>
              <span className={styles.actionLabel}>Manage orders</span>
              <span className={styles.actionDescription}>
                Update status, view details, handle cancellations
              </span>
            </div>
          </Link>
          <Link href="/seller/inventory" className={styles.actionCard}>
            <div className={styles.actionIcon}>📋</div>
            <div className={styles.actionInfo}>
              <span className={styles.actionLabel}>Manage inventory</span>
              <span className={styles.actionDescription}>
                Add, edit, or remove products from your store
              </span>
            </div>
          </Link>
          <Link href="/seller/settings" className={styles.actionCard}>
            <div className={styles.actionIcon}>⚙️</div>
            <div className={styles.actionInfo}>
              <span className={styles.actionLabel}>Settings</span>
              <span className={styles.actionDescription}>
                Delivery radius, store pin, profile
              </span>
            </div>
          </Link>
        </div>
      </div>
    </>
  );
}
