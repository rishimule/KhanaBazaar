"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import StatsCard from "@/components/StatsCard";
import ActiveOrdersWidget from "@/components/orders/ActiveOrdersWidget";
import { MasterProduct, Category, Store, ApplicationCounts } from "@/types";
import styles from "../seller/page.module.css";

export default function AdminDashboardPage() {
  const router = useRouter();
  const { dbUser, token, loading } = useAuth();
  const [products, setProducts] = useState<MasterProduct[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
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
      Promise.all([
        get<MasterProduct[]>("/api/v1/catalog/products", token),
        get<Category[]>("/api/v1/catalog/categories", token),
        get<Store[]>("/api/v1/stores/", token),
        get<ApplicationCounts>("/api/v1/sellers/admin/applications/counts", token),
      ])
        .then(([prods, cats, strs, c]) => {
          setProducts(prods);
          setCategories(cats);
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
        <StatsCard icon="📦" label="Master Products" value={products.length} variant="primary" />
        <StatsCard icon="🏷️" label="Categories" value={categories.length} variant="accent" />
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
          <Link href="/admin/products" className={styles.actionCard}>
            <div className={styles.actionIcon}>📋</div>
            <div className={styles.actionInfo}>
              <span className={styles.actionLabel}>Manage Products</span>
              <span className={styles.actionDescription}>
                Add, edit, or remove products from the master catalog
              </span>
            </div>
          </Link>
          <Link href="/admin/categories" className={styles.actionCard}>
            <div className={styles.actionIcon}>🏷️</div>
            <div className={styles.actionInfo}>
              <span className={styles.actionLabel}>Manage Categories</span>
              <span className={styles.actionDescription}>
                Organize products into browsable categories
              </span>
            </div>
          </Link>
          <Link href="/admin/sellers" className={styles.actionCard}>
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
        </div>
      </div>
    </>
  );
}
