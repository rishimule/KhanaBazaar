"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import StatsCard from "@/components/StatsCard";
import { Store, StoreInventory } from "@/types";
import styles from "./page.module.css";

export default function SellerDashboardPage() {
  const router = useRouter();
  const { dbUser, token, loading } = useAuth();
  const [stores, setStores] = useState<Store[]>([]);
  const [inventory, setInventory] = useState<StoreInventory[]>([]);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (!loading && (!dbUser || dbUser.role !== "seller")) {
      router.push(dbUser ? "/" : "/login");
      return;
    }
    if (!loading && dbUser && token) {
      get<Store[]>("/api/v1/stores/my", token)
        .then(async (myStores) => {
          setStores(myStores);
          // Fetch inventory for first store
          if (myStores.length > 0) {
            const inv = await get<StoreInventory[]>(
              `/api/v1/stores/${myStores[0].id}/inventory/all`,
              token
            );
            setInventory(inv);
          }
        })
        .catch(() => {})
        .finally(() => setFetching(false));
    }
  }, [loading, dbUser, token, router]);

  if (loading || fetching) {
    return <div style={{ padding: "2rem", textAlign: "center", color: "var(--color-neutral-500)" }}>Loading…</div>;
  }

  const store = stores[0];
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
          value={store?.is_active ? "Active" : "Inactive"}
          variant={store?.is_active ? "accent" : "warning"}
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
          {store && (
            <Link href={`/stores/${store.id}`} className={styles.actionCard}>
              <div className={styles.actionIcon}>👁️</div>
              <div className={styles.actionInfo}>
                <span className={styles.actionLabel}>View Storefront</span>
                <span className={styles.actionDescription}>
                  See how customers see your store
                </span>
              </div>
            </Link>
          )}
        </div>
      </div>
    </>
  );
}
