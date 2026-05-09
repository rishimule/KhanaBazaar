"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/AuthContext";
import { get, patch } from "@/lib/api";
import StatsCard from "@/components/StatsCard";
import ActiveOrdersWidget from "@/components/orders/ActiveOrdersWidget";
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

  const updateRadius = async (km: number) => {
    if (!store || !token) return;
    try {
      const updated = await patch<Store>(
        `/api/v1/stores/${store.id}`,
        { delivery_radius_km: km },
        token,
      );
      setStores((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
    } catch {
      /* ignore — UI keeps the previous value */
    }
  };

  return (
    <>
      {store && !store.pin_confirmed && (
        <div className={styles.pinBanner}>
          <strong>Confirm your store pin.</strong> Customers can&apos;t find
          you on the map yet — drop a pin from your business address page.
        </div>
      )}

      <ActiveOrdersWidget role="seller" limit={10} />

      {store && (
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>Delivery radius</h2>
          </div>
          <div className={styles.radiusRow}>
            <label htmlFor="delivery-radius" className={styles.radiusLabel}>
              Delivers within{" "}
              <strong>{store.delivery_radius_km.toFixed(1)} km</strong>
            </label>
            <input
              id="delivery-radius"
              type="range"
              min={0.5}
              max={50}
              step={0.5}
              value={store.delivery_radius_km}
              onChange={(e) => void updateRadius(parseFloat(e.target.value))}
            />
          </div>
        </div>
      )}

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
