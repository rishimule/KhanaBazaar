"use client";

import { use, useState, useMemo, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import { Store, StoreInventory, MasterProduct, Category } from "@/types";
import ProductCard from "@/components/ProductCard";
import styles from "./page.module.css";

/** Enriched inventory item with product details for display. */
interface InventoryWithProduct extends StoreInventory {
  product: MasterProduct;
}

interface Props {
  params: Promise<{ id: string }>;
}

export default function StoreDetailPage({ params }: Props) {
  const { id } = use(params);
  const storeId = parseInt(id, 10);
  const router = useRouter();
  const { dbUser, loading: authLoading } = useAuth();

  const [store, setStore] = useState<Store | null>(null);
  const [inventory, setInventory] = useState<InventoryWithProduct[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [fetching, setFetching] = useState(true);
  const [activeCategory, setActiveCategory] = useState<number | null>(null);

  useEffect(() => {
    if (!authLoading && !dbUser) {
      router.push("/login");
      return;
    }
    if (!authLoading && dbUser) {
      Promise.all([
        get<Store>(`/api/v1/stores/${storeId}`),
        get<StoreInventory[]>(`/api/v1/stores/${storeId}/inventory`),
        get<MasterProduct[]>("/api/v1/catalog/products"),
        get<Category[]>("/api/v1/catalog/categories"),
      ])
        .then(([storeData, invData, products, cats]) => {
          setStore(storeData);
          setCategories(cats);
          // Enrich inventory with product data
          const productMap = new Map(products.map((p) => [p.id, p]));
          const enriched = invData
            .map((inv) => ({
              ...inv,
              product: productMap.get(inv.product_id)!,
            }))
            .filter((inv) => inv.product);
          setInventory(enriched);
        })
        .catch(() => setStore(null))
        .finally(() => setFetching(false));
    }
  }, [authLoading, dbUser, storeId, router]);

  // Get unique categories from this store's inventory
  const storeCategories = useMemo(() => {
    const catIds = [...new Set(inventory.map((i) => i.product.category_id))];
    return categories.filter((c) => catIds.includes(c.id));
  }, [inventory, categories]);

  // Filter inventory by selected category
  const filteredInventory = useMemo(() => {
    if (activeCategory === null) return inventory;
    return inventory.filter((i) => i.product.category_id === activeCategory);
  }, [inventory, activeCategory]);

  if (authLoading || fetching) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <div style={{ textAlign: "center", padding: "4rem 0", color: "var(--color-neutral-500)" }}>
            Loading…
          </div>
        </div>
      </div>
    );
  }

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

  const getCategoryName = (catId: number) =>
    categories.find((c) => c.id === catId)?.name ?? "Other";

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
