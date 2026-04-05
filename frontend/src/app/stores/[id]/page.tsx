"use client";

import { use, useState, useMemo } from "react";
import Link from "next/link";
import { mockStores, mockInventories, mockCategories, getCategoryName } from "@/lib/mock-data";
import { InventoryWithProduct } from "@/types";
import ProductCard from "@/components/ProductCard";
import styles from "./page.module.css";

interface Props {
  params: Promise<{ id: string }>;
}

export default function StoreDetailPage({ params }: Props) {
  const { id } = use(params);
  const storeId = parseInt(id, 10);
  const store = mockStores.find((s) => s.id === storeId);

  // Memoize inventory to stabilize reference
  const inventory: InventoryWithProduct[] = useMemo(
    () => mockInventories[storeId] ?? [],
    [storeId]
  );

  const [activeCategory, setActiveCategory] = useState<number | null>(null);

  // Get unique categories from this store's inventory
  const storeCategories = useMemo(() => {
    const catIds = [...new Set(inventory.map((i) => i.product.category_id))];
    return mockCategories.filter((c) => catIds.includes(c.id));
  }, [inventory]);

  // Filter inventory by selected category
  const filteredInventory = useMemo(() => {
    if (activeCategory === null) return inventory;
    return inventory.filter((i) => i.product.category_id === activeCategory);
  }, [inventory, activeCategory]);

  if (!store) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <div className={styles.notFound}>
            <div className={styles.notFoundIcon}>🔍</div>
            <h1 className={styles.notFoundTitle}>Store Not Found</h1>
            <p className={styles.notFoundText}>
              This store doesn&apos;t exist or may have been removed.
            </p>
            <Link href="/stores" className="btn btn-primary">
              Browse All Stores
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.pageInner}>
        {/* Store Header */}
        <div className={styles.storeHeader}>
          <div className={styles.storeHeaderLeft}>
            <div className={styles.storeIcon}>🏪</div>
            <div className={styles.storeInfo}>
              <h1 className={styles.storeName}>{store.name}</h1>
              <p className={styles.storeAddress}>{store.address}</p>
            </div>
          </div>
          <div className={styles.statusBadge}>● Open Now</div>
        </div>

        {/* Category Tabs */}
        <div className={styles.tabs}>
          <button
            className={`${styles.tab} ${activeCategory === null ? styles.tabActive : ""}`}
            onClick={() => setActiveCategory(null)}
          >
            All ({inventory.length})
          </button>
          {storeCategories.map((cat) => {
            const count = inventory.filter(
              (i) => i.product.category_id === cat.id
            ).length;
            return (
              <button
                key={cat.id}
                className={`${styles.tab} ${activeCategory === cat.id ? styles.tabActive : ""}`}
                onClick={() => setActiveCategory(cat.id)}
              >
                {cat.name} ({count})
              </button>
            );
          })}
        </div>

        {/* Products Grid */}
        {filteredInventory.length > 0 ? (
          <div className={styles.productsGrid}>
            {filteredInventory.map((item) => (
              <ProductCard
                key={item.id}
                item={item}
                storeId={store.id}
                storeName={store.name}
              />
            ))}
          </div>
        ) : (
          <div className={styles.empty}>
            No products found in &quot;{getCategoryName(activeCategory ?? 0)}&quot;
          </div>
        )}
      </div>
    </div>
  );
}
