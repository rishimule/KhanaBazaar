"use client";

import { useState, useMemo, useEffect } from "react";
import Link from "next/link";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import DataTable, { Column } from "@/components/DataTable";
import Modal, { modalStyles } from "@/components/Modal";
import { useAuth } from "@/lib/AuthContext";
import { get, post, put, del } from "@/lib/api";
import {
  Store,
  StoreInventory,
  MasterProduct,
  Category,
  Service,
} from "@/types";

import styles from "./page.module.css";
import mobileStyles from "@/components/DataTableCard.module.css";

interface InventoryWithProduct extends StoreInventory {
  product: MasterProduct;
}

interface CategoryBucket {
  category: Category;
  items: InventoryWithProduct[];
}

interface ServiceBucket {
  service: Service;
  categories: CategoryBucket[];
  totalCount: number;
}

function InventoryServiceTabs({
  buckets,
  activeId,
  onChange,
}: {
  buckets: ServiceBucket[];
  activeId: number | null;
  onChange: (slug: string) => void;
}) {
  if (buckets.length === 0) return null;
  return (
    <div className={styles.serviceTabs} role="tablist">
      {buckets.map(({ service, totalCount }) => {
        const isActive = service.id === activeId;
        return (
          <button
            key={service.id}
            role="tab"
            aria-selected={isActive}
            className={`${styles.serviceTab} ${isActive ? styles.serviceTabActive : ""}`}
            onClick={() => onChange(service.slug)}
          >
            {service.name}
            <span className={styles.serviceTabCount}>({totalCount})</span>
          </button>
        );
      })}
    </div>
  );
}

function InventoryCategoryNav({ categories }: { categories: CategoryBucket[] }) {
  if (categories.length === 0) return null;
  return (
    <nav className={styles.categoryNav} aria-label="Categories">
      {categories.map(({ category, items }) => (
        <a
          key={category.id}
          href={`#cat-${category.id}`}
          className={styles.categoryNavLink}
        >
          {category.name}
          <span className={styles.categoryNavCount}>({items.length})</span>
        </a>
      ))}
    </nav>
  );
}

export default function SellerInventoryPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const activeServiceSlug = searchParams.get("service");
  const { dbUser, token, loading: authLoading } = useAuth();

  const [store, setStore] = useState<Store | null>(null);
  const [inventory, setInventory] = useState<InventoryWithProduct[]>([]);
  const [allProducts, setAllProducts] = useState<MasterProduct[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [fetching, setFetching] = useState(true);

  const [editItem, setEditItem] = useState<InventoryWithProduct | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [formProductId, setFormProductId] = useState<number>(0);
  const [formPrice, setFormPrice] = useState("");
  const [formStock, setFormStock] = useState("");
  const [presetCategoryId, setPresetCategoryId] = useState<number | null>(null);

  useEffect(() => {
    if (!authLoading && (!dbUser || dbUser.role !== "seller")) {
      router.push(dbUser ? "/" : "/login");
      return;
    }
    if (!authLoading && dbUser && token) {
      Promise.all([
        get<Store[]>("/api/v1/stores/my", token),
        get<MasterProduct[]>("/api/v1/catalog/products"),
        get<Category[]>("/api/v1/catalog/categories"),
      ])
        .then(async ([myStores, products, cats]) => {
          setAllProducts(products);
          setCategories(cats);
          if (myStores.length > 0) {
            const s = myStores[0];
            setStore(s);
            const inv = await get<StoreInventory[]>(
              `/api/v1/stores/${s.id}/inventory/all`,
              token
            );
            const productMap = new Map(products.map((p) => [p.id, p]));
            setInventory(
              inv
                .map((i) => ({ ...i, product: productMap.get(i.product_id)! }))
                .filter((i) => i.product)
            );
          }
        })
        .catch(() => {})
        .finally(() => setFetching(false));
    }
  }, [authLoading, dbUser, token, router]);

  const buckets: ServiceBucket[] = useMemo(() => {
    if (!store) return [];
    const catsByService = new Map<number, Category[]>();
    for (const c of categories) {
      const list = catsByService.get(c.service_id) ?? [];
      list.push(c);
      catsByService.set(c.service_id, list);
    }
    const itemsByCategory = new Map<number, InventoryWithProduct[]>();
    for (const item of inventory) {
      const list = itemsByCategory.get(item.product.category_id) ?? [];
      list.push(item);
      itemsByCategory.set(item.product.category_id, list);
    }
    const services = [...store.services].sort(
      (a, b) => a.sort_order - b.sort_order
    );
    return services.map((service) => {
      const serviceCats = (catsByService.get(service.id) ?? []).sort((a, b) =>
        a.name.localeCompare(b.name)
      );
      const categoryBuckets: CategoryBucket[] = serviceCats.map((category) => {
        const items = (itemsByCategory.get(category.id) ?? []).sort(
          (a, b) =>
            a.product.subcategory_name.localeCompare(b.product.subcategory_name) ||
            a.product.name.localeCompare(b.product.name)
        );
        return { category, items };
      });
      const totalCount = categoryBuckets.reduce((n, b) => n + b.items.length, 0);
      return { service, categories: categoryBuckets, totalCount };
    });
  }, [store, categories, inventory]);

  const activeBucket: ServiceBucket | null = useMemo(() => {
    if (buckets.length === 0) return null;
    if (activeServiceSlug) {
      const found = buckets.find((b) => b.service.slug === activeServiceSlug);
      if (found) return found;
    }
    return buckets[0];
  }, [buckets, activeServiceSlug]);

  function setActiveService(slug: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("service", slug);
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  }

  const availableProducts = useMemo(() => {
    const existingIds = new Set(inventory.map((i) => i.product_id));
    return allProducts.filter((p) => !existingIds.has(p.id));
  }, [inventory, allProducts]);

  const columns: Column<InventoryWithProduct>[] = [
    {
      key: "product_name",
      label: "Product",
      render: (row) => <strong>{row.product.name}</strong>,
    },
    {
      key: "subcategory",
      label: "Subcategory",
      render: (row) => row.product.subcategory_name,
    },
    { key: "price", label: "Price (₹)", render: (row) => `₹${row.price}` },
    { key: "stock", label: "Stock", render: (row) => String(row.stock) },
    {
      key: "is_available",
      label: "Status",
      render: (row) => (
        <button
          className={`${styles.toggleBtn} ${
            row.is_available ? styles.toggleActive : styles.toggleInactive
          }`}
          onClick={() => toggleAvailability(row)}
        >
          {row.is_available ? "Available" : "Unavailable"}
        </button>
      ),
    },
  ];

  async function toggleAvailability(item: InventoryWithProduct) {
    if (!store || !token) return;
    try {
      await put(
        `/api/v1/stores/${store.id}/inventory/${item.id}`,
        { is_available: !item.is_available, price: item.price, stock: item.stock },
        token
      );
      setInventory((prev) =>
        prev.map((i) =>
          i.id === item.id ? { ...i, is_available: !i.is_available } : i
        )
      );
    } catch { /* silent */ }
  }

  function handleEdit(item: InventoryWithProduct) {
    setEditItem(item);
    setFormPrice(String(item.price));
    setFormStock(String(item.stock));
  }

  async function handleSaveEdit() {
    if (!editItem || !store || !token) return;
    try {
      await put(
        `/api/v1/stores/${store.id}/inventory/${editItem.id}`,
        {
          price: parseFloat(formPrice) || editItem.price,
          stock: parseInt(formStock, 10) ?? editItem.stock,
          is_available: editItem.is_available,
        },
        token
      );
      setInventory((prev) =>
        prev.map((i) =>
          i.id === editItem.id
            ? {
                ...i,
                price: parseFloat(formPrice) || i.price,
                stock: parseInt(formStock, 10) ?? i.stock,
              }
            : i
        )
      );
      setEditItem(null);
    } catch { /* silent */ }
  }

  async function handleDelete(item: InventoryWithProduct) {
    if (!store || !token) return;
    try {
      await del(`/api/v1/stores/${store.id}/inventory/${item.id}`, token);
      setInventory((prev) => prev.filter((i) => i.id !== item.id));
    } catch { /* silent */ }
  }

  function openAdd(categoryId?: number) {
    const pool = categoryId
      ? availableProducts.filter((p) => p.category_id === categoryId)
      : availableProducts;
    setPresetCategoryId(categoryId ?? null);
    setFormProductId(pool[0]?.id ?? 0);
    setFormPrice("");
    setFormStock("");
    setShowAdd(true);
  }

  async function handleAdd() {
    if (!store || !token) return;
    const product = allProducts.find((p) => p.id === formProductId);
    if (!product) return;
    try {
      const created = await post<StoreInventory>(
        `/api/v1/stores/${store.id}/inventory`,
        {
          product_id: product.id,
          price: parseFloat(formPrice) || product.base_price,
          stock: parseInt(formStock, 10) || 0,
          is_available: true,
        },
        token
      );
      setInventory((prev) => [...prev, { ...created, product }]);
      setShowAdd(false);
      setPresetCategoryId(null);
    } catch { /* silent */ }
  }

  if (authLoading || fetching) {
    return (
      <div style={{ padding: "2rem", textAlign: "center", color: "var(--color-neutral-500)" }}>
        Loading…
      </div>
    );
  }

  return (
    <>
      <div className={styles.toolbar}>
        <span className={styles.toolbarLeft}>
          {inventory.length} products in store
        </span>
        <Link href="/seller/inventory/bulk" className="btn btn-outline">
          Bulk edit →
        </Link>
        <button
          className={styles.addBtn}
          onClick={() => openAdd()}
          disabled={availableProducts.length === 0}
        >
          + Add Product
        </button>
      </div>

      <InventoryServiceTabs
        buckets={buckets}
        activeId={activeBucket?.service.id ?? null}
        onChange={setActiveService}
      />

      {activeBucket && (
        <InventoryCategoryNav categories={activeBucket.categories} />
      )}

      {buckets.length === 0 && (
        <div className={styles.servicesEmpty}>
          No services linked to this store. Contact admin.
        </div>
      )}

      {activeBucket?.categories.map((bucket) => (
        <section
          key={bucket.category.id}
          id={`cat-${bucket.category.id}`}
          className={styles.categorySection}
        >
          <header className={styles.categoryHeader}>
            <h2 className={styles.categoryTitle}>
              {bucket.category.name}
              <span className={styles.categoryCount}>({bucket.items.length})</span>
            </h2>
            <button
              className={styles.categoryAddBtn}
              onClick={() => openAdd(bucket.category.id)}
              disabled={
                availableProducts.filter((p) => p.category_id === bucket.category.id)
                  .length === 0
              }
            >
              + Add
            </button>
          </header>
          {bucket.items.length === 0 ? (
            <div className={styles.emptyCategory}>
              No products in this category yet.{" "}
              <button
                className={styles.categoryAddBtn}
                style={{ marginLeft: "var(--space-2)" }}
                onClick={() => openAdd(bucket.category.id)}
                disabled={
                  availableProducts.filter((p) => p.category_id === bucket.category.id)
                    .length === 0
                }
              >
                + Add
              </button>
            </div>
          ) : (
            <DataTable
              columns={columns}
              data={bucket.items}
              keyField="id"
              onEdit={handleEdit}
              onDelete={handleDelete}
              mobileCardRender={(row) => (
                <>
                  <div className={mobileStyles.cardTopRow}>
                    <span className={mobileStyles.cardTitle}>{row.product.name}</span>
                    <span className={mobileStyles.cardPriceRight}>₹{row.price}</span>
                  </div>
                  <div className={mobileStyles.cardMeta}>
                    {row.product.subcategory_name} • Stock: {row.stock}
                  </div>
                  <button
                    className={`${styles.toggleBtn} ${
                      row.is_available ? styles.toggleActive : styles.toggleInactive
                    }`}
                    style={{ width: "100%", minHeight: 44 }}
                    onClick={() => toggleAvailability(row)}
                  >
                    {row.is_available ? "Available" : "Unavailable"}
                  </button>
                </>
              )}
            />
          )}
        </section>
      ))}

      {editItem && (
        <Modal
          title={`Edit — ${editItem.product.name}`}
          onClose={() => setEditItem(null)}
          footer={
            <>
              <button className="btn btn-outline" onClick={() => setEditItem(null)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleSaveEdit}>Save Changes</button>
            </>
          }
        >
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Price (₹)</label>
            <input
              type="number"
              className={modalStyles.input}
              value={formPrice}
              onChange={(e) => setFormPrice(e.target.value)}
              min="0"
              step="0.01"
            />
          </div>
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Stock</label>
            <input
              type="number"
              className={modalStyles.input}
              value={formStock}
              onChange={(e) => setFormStock(e.target.value)}
              min="0"
            />
          </div>
        </Modal>
      )}

      {showAdd && (
        <Modal
          title="Add Product to Store"
          onClose={() => { setShowAdd(false); setPresetCategoryId(null); }}
          footer={
            <>
              <button
                className="btn btn-outline"
                onClick={() => { setShowAdd(false); setPresetCategoryId(null); }}
              >
                Cancel
              </button>
              <button className="btn btn-primary" onClick={handleAdd}>Add Product</button>
            </>
          }
        >
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Product</label>
            <select
              className={modalStyles.select}
              value={formProductId}
              onChange={(e) => setFormProductId(parseInt(e.target.value, 10))}
            >
              {availableProducts
                .filter((p) =>
                  presetCategoryId == null ? true : p.category_id === presetCategoryId
                )
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} — ₹{p.base_price}
                  </option>
                ))}
            </select>
          </div>
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Your Price (₹)</label>
            <input
              type="number"
              className={modalStyles.input}
              value={formPrice}
              onChange={(e) => setFormPrice(e.target.value)}
              placeholder="Leave blank to use base price"
              min="0"
              step="0.01"
            />
          </div>
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Stock Quantity</label>
            <input
              type="number"
              className={modalStyles.input}
              value={formStock}
              onChange={(e) => setFormStock(e.target.value)}
              placeholder="0"
              min="0"
            />
          </div>
        </Modal>
      )}
    </>
  );
}
