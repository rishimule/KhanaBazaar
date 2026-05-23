"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import StatsCard from "@/components/StatsCard";
import styles from "../seller/page.module.css";

interface AdminMetrics {
  active_orders: number;
  orders_today: number;
  orders_this_month: number;
  gmv_this_month: number;
  active_master_products: number;
  active_categories: number;
  active_stores: number;
  pending_applications: number;
  approved_sellers: number;
}

export default function AdminDashboardPage() {
  const router = useRouter();
  const { dbUser, token, loading } = useAuth();
  const [metrics, setMetrics] = useState<AdminMetrics | null>(null);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (!loading && (!dbUser || dbUser.role !== "admin")) {
      router.push(dbUser ? "/" : "/login");
      return;
    }
    if (!loading && dbUser && token) {
      get<AdminMetrics>("/api/v1/admin/metrics", token)
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
    gmv_this_month: 0,
    active_master_products: 0,
    active_categories: 0,
    active_stores: 0,
    pending_applications: 0,
    approved_sellers: 0,
  };

  return (
    <>
      <div className={styles.statsGrid}>
        <StatsCard
          icon="📦"
          label="Active orders"
          value={m.active_orders}
          variant={m.active_orders > 0 ? "primary" : "info"}
        />
        <StatsCard icon="🗓️" label="Orders today" value={m.orders_today} variant="accent" />
        <StatsCard icon="📈" label="Orders this month" value={m.orders_this_month} variant="info" />
        <StatsCard
          icon="💰"
          label="GMV (delivered, this month)"
          value={`₹${m.gmv_this_month.toFixed(0)}`}
          variant="accent"
        />
        <StatsCard
          icon="📦"
          label="Master products (active)"
          value={m.active_master_products}
          variant="primary"
        />
        <StatsCard
          icon="🏷️"
          label="Categories (active)"
          value={m.active_categories}
          variant="accent"
        />
        <StatsCard icon="🏪" label="Active stores" value={m.active_stores} variant="info" />
        <StatsCard
          icon="⏳"
          label="Pending applications"
          value={m.pending_applications}
          trend={m.pending_applications > 0 ? "requires review" : "all caught up"}
          trendDirection={m.pending_applications > 0 ? "up" : "down"}
          variant={m.pending_applications > 0 ? "warning" : "info"}
        />
        <StatsCard
          icon="🤝"
          label="Approved sellers"
          value={m.approved_sellers}
          variant="primary"
        />
      </div>

      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Quick actions</h2>
        </div>
        <div className={styles.quickActions}>
          <Link href="/admin/orders" className={styles.actionCard}>
            <div className={styles.actionIcon}>📦</div>
            <div className={styles.actionInfo}>
              <span className={styles.actionLabel}>All orders</span>
              <span className={styles.actionDescription}>
                Browse, search, and act on every order
              </span>
            </div>
          </Link>
          <Link href="/admin/catalog" className={styles.actionCard}>
            <div className={styles.actionIcon}>🗂️</div>
            <div className={styles.actionInfo}>
              <span className={styles.actionLabel}>Manage catalog</span>
              <span className={styles.actionDescription}>
                Services, categories, subcategories, products
              </span>
            </div>
          </Link>
          <Link href="/admin/sellers/applications" className={styles.actionCard}>
            <div className={styles.actionIcon}>✅</div>
            <div className={styles.actionInfo}>
              <span className={styles.actionLabel}>
                Review applications{m.pending_applications > 0 ? ` (${m.pending_applications})` : ""}
              </span>
              <span className={styles.actionDescription}>
                Approve, reject, or revoke seller accounts
              </span>
            </div>
          </Link>
          <Link href="/admin/sellers" className={styles.actionCard}>
            <div className={styles.actionIcon}>🏪</div>
            <div className={styles.actionInfo}>
              <span className={styles.actionLabel}>Approved sellers</span>
              <span className={styles.actionDescription}>
                Drill into any seller&apos;s store, edit inventory, manage orders
              </span>
            </div>
          </Link>
        </div>
      </div>
    </>
  );
}
