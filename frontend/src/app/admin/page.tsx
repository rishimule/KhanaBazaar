"use client";

import Link from "next/link";
import StatsCard from "@/components/StatsCard";
import { mockProducts, mockCategories, mockStores } from "@/lib/mock-data";
import styles from "../seller/page.module.css";

export default function AdminDashboardPage() {
  return (
    <>
      {/* Stats */}
      <div className={styles.statsGrid}>
        <StatsCard
          icon="📦"
          label="Master Products"
          value={mockProducts.length}
          variant="primary"
        />
        <StatsCard
          icon="🏷️"
          label="Categories"
          value={mockCategories.length}
          variant="accent"
        />
        <StatsCard
          icon="🏪"
          label="Active Stores"
          value={mockStores.filter((s) => s.is_active).length}
          variant="info"
        />
        <StatsCard
          icon="👥"
          label="Total Sellers"
          value={mockStores.length}
          trend="registered on platform"
          trendDirection="up"
          variant="warning"
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
        </div>
      </div>
    </>
  );
}
