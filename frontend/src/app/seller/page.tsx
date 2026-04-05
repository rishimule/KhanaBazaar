"use client";

import Link from "next/link";
import StatsCard from "@/components/StatsCard";
import { mockInventories, mockStores } from "@/lib/mock-data";
import styles from "./page.module.css";

// Simulating seller is the owner of store ID 1
const SELLER_STORE_ID = 1;

export default function SellerDashboardPage() {
  const store = mockStores.find((s) => s.id === SELLER_STORE_ID)!;
  const inventory = mockInventories[SELLER_STORE_ID] ?? [];
  const totalStock = inventory.reduce((sum, i) => sum + i.stock, 0);
  const availableCount = inventory.filter((i) => i.is_available).length;

  return (
    <>
      {/* Stats */}
      <div className={styles.statsGrid}>
        <StatsCard
          icon="📦"
          label="Total Products"
          value={inventory.length}
          variant="primary"
        />
        <StatsCard
          icon="🏷️"
          label="Total Stock"
          value={totalStock}
          trend="units across all products"
          trendDirection="up"
          variant="accent"
        />
        <StatsCard
          icon="✅"
          label="Available"
          value={`${availableCount} / ${inventory.length}`}
          variant="info"
        />
        <StatsCard
          icon="🏪"
          label="Store Status"
          value={store.is_active ? "Active" : "Inactive"}
          variant={store.is_active ? "accent" : "warning"}
        />
      </div>

      {/* Quick Actions */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Quick Actions</h2>
        </div>
        <div className={styles.quickActions}>
          <Link href="/seller/inventory" className={styles.actionCard}>
            <div className={styles.actionIcon}>📋</div>
            <div className={styles.actionInfo}>
              <span className={styles.actionLabel}>Manage Inventory</span>
              <span className={styles.actionDescription}>
                Add, edit, or remove products from your store
              </span>
            </div>
          </Link>
          <Link href={`/stores/${SELLER_STORE_ID}`} className={styles.actionCard}>
            <div className={styles.actionIcon}>👁️</div>
            <div className={styles.actionInfo}>
              <span className={styles.actionLabel}>View Storefront</span>
              <span className={styles.actionDescription}>
                See how customers see your store
              </span>
            </div>
          </Link>
        </div>
      </div>
    </>
  );
}
