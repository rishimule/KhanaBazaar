"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
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
  const t = useTranslations("Admin.dashboard");
  const tc = useTranslations("Admin.common");
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
        {tc("loading")}
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
          label={t("activeOrders")}
          value={m.active_orders}
          variant={m.active_orders > 0 ? "primary" : "info"}
        />
        <StatsCard icon="🗓️" label={t("ordersToday")} value={m.orders_today} variant="accent" />
        <StatsCard icon="📈" label={t("ordersThisMonth")} value={m.orders_this_month} variant="info" />
        <StatsCard
          icon="💰"
          label={t("gmvThisMonth")}
          value={`₹${m.gmv_this_month.toFixed(0)}`}
          variant="accent"
        />
        <StatsCard
          icon="📦"
          label={t("masterProducts")}
          value={m.active_master_products}
          variant="primary"
        />
        <StatsCard
          icon="🏷️"
          label={t("categories")}
          value={m.active_categories}
          variant="accent"
        />
        <StatsCard icon="🏪" label={t("activeStores")} value={m.active_stores} variant="info" />
        <StatsCard
          icon="⏳"
          label={t("pendingApplications")}
          value={m.pending_applications}
          trend={m.pending_applications > 0 ? t("requiresReview") : t("allCaughtUp")}
          trendDirection={m.pending_applications > 0 ? "up" : "down"}
          variant={m.pending_applications > 0 ? "warning" : "info"}
        />
        <StatsCard
          icon="🤝"
          label={t("approvedSellers")}
          value={m.approved_sellers}
          variant="primary"
        />
      </div>

      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>{t("quickActions")}</h2>
        </div>
        <div className={styles.quickActions}>
          <Link href="/admin/orders" className={styles.actionCard}>
            <div className={styles.actionIcon}>📦</div>
            <div className={styles.actionInfo}>
              <span className={styles.actionLabel}>{t("allOrders")}</span>
              <span className={styles.actionDescription}>
                {t("allOrdersDesc")}
              </span>
            </div>
          </Link>
          <Link href="/admin/catalog" className={styles.actionCard}>
            <div className={styles.actionIcon}>🗂️</div>
            <div className={styles.actionInfo}>
              <span className={styles.actionLabel}>{t("manageCatalog")}</span>
              <span className={styles.actionDescription}>
                {t("manageCatalogDesc")}
              </span>
            </div>
          </Link>
          <Link href="/admin/sellers/applications" className={styles.actionCard}>
            <div className={styles.actionIcon}>✅</div>
            <div className={styles.actionInfo}>
              <span className={styles.actionLabel}>
                {m.pending_applications > 0
                  ? t("reviewApplicationsCount", { count: m.pending_applications })
                  : t("reviewApplications")}
              </span>
              <span className={styles.actionDescription}>
                {t("reviewApplicationsDesc")}
              </span>
            </div>
          </Link>
          <Link href="/admin/sellers" className={styles.actionCard}>
            <div className={styles.actionIcon}>🏪</div>
            <div className={styles.actionInfo}>
              <span className={styles.actionLabel}>{t("approvedSellersAction")}</span>
              <span className={styles.actionDescription}>
                {t("approvedSellersDesc")}
              </span>
            </div>
          </Link>
        </div>
      </div>
    </>
  );
}
