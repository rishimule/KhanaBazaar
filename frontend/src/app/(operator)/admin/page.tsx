"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import StatsCard from "@/components/StatsCard";
import ActiveOrdersWidget from "@/components/orders/ActiveOrdersWidget";
import {
  ApplicationCounts,
  CatalogEntity,
  PagedResponse,
  Store,
} from "@/types";
import styles from "../seller/page.module.css";

export default function AdminDashboardPage() {
  const router = useRouter();
  const { dbUser, token, loading } = useAuth();
  const [productCount, setProductCount] = useState(0);
  const [categoryCount, setCategoryCount] = useState(0);
  const [stores, setStores] = useState<Store[]>([]);
  const [counts, setCounts] = useState<ApplicationCounts>({
    pending: 0, approved: 0, rejected: 0, total: 0,
  });
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (!loading && (!dbUser || dbUser.role !== "admin")) {
      router.push(dbUser ? "/" : "/login");
      return;
    }
    if (!loading && dbUser && token) {
      // page_size=1 keeps the response tiny; only `total` is used.
      Promise.all([
        get<PagedResponse<CatalogEntity>>(
          "/api/v1/catalog/admin/products?is_active=true&page=1&page_size=1",
          token,
        ),
        get<PagedResponse<CatalogEntity>>(
          "/api/v1/catalog/admin/categories?is_active=true&page=1&page_size=1",
          token,
        ),
        get<Store[]>("/api/v1/stores/", token),
        get<ApplicationCounts>("/api/v1/sellers/admin/applications/counts", token),
      ])
        .then(([prods, cats, strs, c]) => {
          setProductCount(prods.total);
          setCategoryCount(cats.total);
          setStores(strs);
          setCounts(c);
        })
        .catch(() => {})
        .finally(() => setFetching(false));
    }
  }, [loading, dbUser, token, router]);

  if (loading || fetching) {
    return <div style={{ padding: "2rem", textAlign: "center", color: "var(--color-neutral-500)" }}>Loading…</div>;
  }

  return (
    <>
      <ActiveOrdersWidget role="admin" limit={10} />

      {/* Stats */}
      <div className={styles.statsGrid}>
        <StatsCard icon="📦" label="Master Products" value={productCount} variant="primary" />
        <StatsCard icon="🏷️" label="Categories" value={categoryCount} variant="accent" />
        <StatsCard icon="🏪" label="Active Stores" value={stores.filter((s) => s.is_active).length} variant="info" />
        <StatsCard
          icon="⏳"
          label="Pending Approvals"
          value={counts.pending}
          trend={counts.pending > 0 ? "requires review" : "all caught up"}
          trendDirection={counts.pending > 0 ? "up" : "down"}
          variant={counts.pending > 0 ? "warning" : "info"}
        />
      </div>

      {/* Quick Actions */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Quick Actions</h2>
        </div>
        <div className={styles.quickActions}>
          <Link href="/admin/catalog" className={styles.actionCard}>
            <div className={styles.actionIcon}>🗂️</div>
            <div className={styles.actionInfo}>
              <span className={styles.actionLabel}>Manage Catalog</span>
              <span className={styles.actionDescription}>
                Drill from services to categories, subcategories, and products
              </span>
            </div>
          </Link>
          <Link href="/admin/sellers/applications" className={styles.actionCard}>
            <div className={styles.actionIcon}>✅</div>
            <div className={styles.actionInfo}>
              <span className={styles.actionLabel}>
                Review Seller Applications{counts.pending > 0 ? ` (${counts.pending})` : ""}
              </span>
              <span className={styles.actionDescription}>
                Approve, reject, or revoke seller accounts
              </span>
            </div>
          </Link>
          <Link href="/admin/sellers" className={styles.actionCard}>
            <div className={styles.actionIcon}>🏪</div>
            <div className={styles.actionInfo}>
              <span className={styles.actionLabel}>Approved Sellers</span>
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
