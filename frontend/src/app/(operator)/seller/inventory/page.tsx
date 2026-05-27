"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useState, useMemo, useEffect } from "react";
import Link from "next/link";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import DataTable, { Column } from "@/components/DataTable";
import Modal, { modalStyles } from "@/components/Modal";
import { useAuth } from "@/lib/AuthContext";
import { get, post, put, del } from "@/lib/api";
import {
  Store,
  StoreInventory,
  EligibleProduct,
  Category,
  Service,
} from "@/types";

import { ScrollRail } from "@/components/ScrollRail";
import { serviceGlyph } from "@/lib/serviceGlyph";

import styles from "./page.module.css";
import mobileStyles from "@/components/DataTableCard.module.css";

interface InventoryWithProduct extends StoreInventory {
  product: EligibleProduct;
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
  const t = useTranslations("Seller.inventory");
  if (buckets.length === 0) return null;
  return (
    <div className={styles.serviceTileRail}>
      <ScrollRail ariaLabel={t("servicesAria")}>
        {buckets.map(({ service, totalCount }) => {
          const isActive = service.id === activeId;
          return (
            <button
              key={service.id}
              type="button"
              className={`${styles.svcTile} ${isActive ? styles.svcTileActive : ""}`}
              onClick={() => onChange(service.slug)}
              aria-current={isActive ? "true" : undefined}
            >
              <span className={styles.svcTileGlyph} aria-hidden>
                {serviceGlyph(service.slug)}
              </span>
              <span className={styles.svcTileLabel}>{service.name}</span>
              <span className={styles.svcTileCount}>{totalCount}</span>
            </button>
          );
        })}
      </ScrollRail>
    </div>
  );
}

function InventoryCategoryNav({ categories }: { categories: CategoryBucket[] }) {
  const t = useTranslations("Seller.inventory");
  if (categories.length === 0) return null;
  return (
    <nav className={styles.categoryNav} aria-label={t("categoriesAria")}>
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
  const t = useTranslations("Seller.inventory");
  const tc = useTranslations("Seller.common");
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const activeServiceSlug = searchParams.get("service");
  const { dbUser, token, loading: authLoading } = useAuth();

  const [store, setStore] = useState<Store | null>(null);
  const [inventory, setInventory] = useState<InventoryWithProduct[]>([]);
  const [allProducts, setAllProducts] = useState<EligibleProduct[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [fetching, setFetching] = useState(true);

  const [editItem, setEditItem] = useState<InventoryWithProduct | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [formProductId, setFormProductId] = useState<number>(0);
  const [formPrice, setFormPrice] = useState("");
  const [formStock, setFormStock] = useState("");
  const [presetCategoryId, setPresetCategoryId] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    if (!authLoading && (!dbUser || dbUser.role !== "seller")) {
      router.push(dbUser ? "/" : "/login");
      return;
    }
    if (!authLoading && dbUser && token) {
      Promise.all([
        get<Store[]>("/api/v1/stores/my", token),
        get<EligibleProduct[]>("/api/v1/sellers/me/eligible-products", token),
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
      label: t("colProduct"),
      render: (row) => <strong>{row.product.name}</strong>,
    },
    {
      key: "subcategory",
      label: t("colSubcategory"),
      render: (row) => row.product.subcategory_name,
    },
    { key: "price", label: t("colPrice"), render: (row) => `₹${row.price}` },
    { key: "stock", label: t("colStock"), render: (row) => String(row.stock) },
    {
      key: "is_available",
      label: t("colStatus"),
      render: (row) => (
        <button
          className={`${styles.toggleBtn} ${
            row.is_available ? styles.toggleActive : styles.toggleInactive
          }`}
          onClick={() => toggleAvailability(row)}
        >
          {row.is_available ? t("available") : t("unavailable")}
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
    setSearchQuery("");
    setShowAll(false);
    setShowAdd(true);
  }

  function closeAdd() {
    setShowAdd(false);
    setPresetCategoryId(null);
    setSearchQuery("");
    setShowAll(false);
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
      closeAdd();
    } catch { /* silent */ }
  }

  if (authLoading || fetching) {
    return (
      <div style={{ padding: "2rem", textAlign: "center", color: "var(--color-neutral-500)" }}>
        {tc("loading")}
      </div>
    );
  }

  return (
    <>
      <div className={styles.toolbar}>
        <span className={styles.toolbarLeft}>
          {t("productCount", { count: inventory.length })}
        </span>
        <Link href="/seller/inventory/bulk" className="btn btn-outline">
          {t("bulkEdit")}
        </Link>
        <button
          className={styles.addBtn}
          onClick={() => openAdd()}
          disabled={availableProducts.length === 0}
        >
          {t("addProduct")}
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
          {t("noServices")}
        </div>
      )}

      {activeBucket && activeBucket.categories.length === 0 && (
        <div className={styles.servicesEmpty}>
          {t("noCategories")}
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
            >
              {t("addShort")}
            </button>
          </header>
          {bucket.items.length === 0 ? (
            <div className={styles.emptyCategory}>
              {t("noProductsInCategory")}{" "}
              <button
                className={styles.categoryAddBtn}
                style={{ marginLeft: "var(--space-2)" }}
                onClick={() => openAdd(bucket.category.id)}
              >
                {t("addShort")}
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
                    {row.product.subcategory_name} • {t("stockMobile", { stock: row.stock })}
                  </div>
                  <button
                    className={`${styles.toggleBtn} ${
                      row.is_available ? styles.toggleActive : styles.toggleInactive
                    }`}
                    style={{ width: "100%", minHeight: 44 }}
                    onClick={() => toggleAvailability(row)}
                  >
                    {row.is_available ? t("available") : t("unavailable")}
                  </button>
                </>
              )}
            />
          )}
        </section>
      ))}

      {editItem && (
        <Modal
          title={t("editTitle", { name: editItem.product.name })}
          onClose={() => setEditItem(null)}
          footer={
            <>
              <button className="btn btn-outline" onClick={() => setEditItem(null)}>{tc("cancel")}</button>
              <button className="btn btn-primary" onClick={handleSaveEdit}>{t("saveChanges")}</button>
            </>
          }
        >
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>{t("priceLabel")}</label>
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
            <label className={modalStyles.label}>{t("stockFieldLabel")}</label>
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

      {showAdd && (() => {
        const presetActive = presetCategoryId !== null && !showAll;
        const presetPool = presetActive
          ? availableProducts.filter((p) => p.category_id === presetCategoryId)
          : availableProducts;
        const q = searchQuery.trim().toLowerCase();
        const visibleProducts = q
          ? presetPool.filter((p) => p.name.toLowerCase().includes(q))
          : presetPool;
        const selectionValid = visibleProducts.some((p) => p.id === formProductId);

        return (
        <Modal
          title={t("addTitle")}
          onClose={closeAdd}
          footer={
            <>
              <button className="btn btn-outline" onClick={closeAdd}>
                {tc("cancel")}
              </button>
              <button
                className="btn btn-primary"
                onClick={handleAdd}
                disabled={!selectionValid}
              >
                {t("addToStore")}
              </button>
            </>
          }
        >
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>{t("productLabel")}</label>
            <input
              type="search"
              className={styles.searchInput}
              placeholder={t("searchPlaceholder")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <div
              className={styles.productList}
              style={{ marginTop: "var(--space-2)" }}
            >
              {visibleProducts.length === 0 ? (
                <div className={styles.productListEmpty}>
                  {q ? (
                    t("noMatch", { query: searchQuery })
                  ) : presetActive ? (
                    <>
                      {t("allInCategory")}
                      <br />
                      <button
                        type="button"
                        className={styles.showAllBtn}
                        onClick={() => setShowAll(true)}
                      >
                        {t("showAll")}
                      </button>
                    </>
                  ) : (
                    t("allInInventory")
                  )}
                </div>
              ) : (
                visibleProducts.map((p) => {
                  const selected = p.id === formProductId;
                  return (
                    <button
                      type="button"
                      key={p.id}
                      className={`${styles.productListRow} ${
                        selected ? styles.productListRowSelected : ""
                      }`}
                      onClick={() => setFormProductId(p.id)}
                    >
                      <span>{p.name}</span>
                      <span style={{ color: "var(--color-neutral-500)" }}>
                        ₹{p.base_price}
                      </span>
                    </button>
                  );
                })
              )}
            </div>
          </div>
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>{t("yourPriceLabel")}</label>
            <input
              type="number"
              className={modalStyles.input}
              value={formPrice}
              onChange={(e) => setFormPrice(e.target.value)}
              placeholder={t("yourPricePlaceholder")}
              min="0"
              step="0.01"
            />
          </div>
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>{t("stockQtyLabel")}</label>
            <input
              type="number"
              className={modalStyles.input}
              value={formStock}
              onChange={(e) => setFormStock(e.target.value)}
              placeholder={t("stockQtyPlaceholder")}
              min="0"
            />
          </div>
        </Modal>
        );
      })()}
    </>
  );
}
