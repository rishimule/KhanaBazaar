"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { use, useState, useMemo, useEffect, useCallback } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { get } from "@/lib/api";
import { formatAddress } from "@/lib/format-address";
import {
  Store,
  StoreInventory,
  MasterProduct,
  Category,
  Service,
  Subcategory,
} from "@/types";
import ProductCard from "@/components/ProductCard";
import CategorySidebar from "@/components/CategorySidebar";
import CartRail from "@/components/CartRail";
import styles from "./page.module.css";

interface InventoryWithProduct extends StoreInventory {
  product: MasterProduct;
}

interface SubcategoryNode {
  subcategory: Subcategory;
  items: InventoryWithProduct[];
}

interface CategoryNode {
  category: Category;
  subcategories: SubcategoryNode[];
  items: InventoryWithProduct[];
}

interface ServiceNode {
  service: Service;
  categories: CategoryNode[];
  totalItems: number;
}

interface Props {
  params: Promise<{ id: string }>;
}

const CATEGORY_ANCHOR = (id: number) => `category-${id}`;
const SCROLL_OFFSET = 96;

/** Emoji per service slug — falls back to 🛒. */
const SERVICE_GLYPH: Record<string, string> = {
  grocery: "🛒",
  food: "🍱",
  pharmacy: "💊",
  electronics: "🔌",
  bakery: "🍞",
  fresh: "🥬",
};

/** Emoji per category — fallback uses service glyph. */
const CATEGORY_GLYPH: Record<string, string> = {
  fruits: "🍅",
  vegetables: "🥦",
  dairy: "🥛",
  bakery: "🍞",
  staples: "🌾",
  snacks: "🍿",
  beverages: "🍵",
  meat: "🍖",
  seafood: "🦐",
  frozen: "🥟",
  instant: "🍜",
  seasoning: "🌶️",
  personal: "🧴",
};

function categoryGlyph(name: string, serviceSlug?: string): string {
  const k = name.toLowerCase();
  for (const key in CATEGORY_GLYPH) {
    if (k.includes(key)) return CATEGORY_GLYPH[key];
  }
  return SERVICE_GLYPH[serviceSlug ?? ""] ?? "🛍️";
}

function buildTree(
  inventory: InventoryWithProduct[],
  services: Service[],
  categories: Category[],
  subcategories: Subcategory[]
): ServiceNode[] {
  const categoryById = new Map(categories.map((c) => [c.id, c]));
  const subcategoryById = new Map(subcategories.map((s) => [s.id, s]));
  const serviceById = new Map(services.map((s) => [s.id, s]));

  const serviceNodes = new Map<number, ServiceNode>();

  for (const item of inventory) {
    const product = item.product;
    const subcategory = subcategoryById.get(product.subcategory_id);
    const category = categoryById.get(product.category_id);
    if (!category) continue;
    const service = serviceById.get(category.service_id);
    if (!service) continue;

    let serviceNode = serviceNodes.get(service.id);
    if (!serviceNode) {
      serviceNode = { service, categories: [], totalItems: 0 };
      serviceNodes.set(service.id, serviceNode);
    }

    let categoryNode = serviceNode.categories.find((c) => c.category.id === category.id);
    if (!categoryNode) {
      categoryNode = { category, subcategories: [], items: [] };
      serviceNode.categories.push(categoryNode);
    }
    categoryNode.items.push(item);
    serviceNode.totalItems += 1;

    if (subcategory) {
      let subNode = categoryNode.subcategories.find(
        (s) => s.subcategory.id === subcategory.id
      );
      if (!subNode) {
        subNode = { subcategory, items: [] };
        categoryNode.subcategories.push(subNode);
      }
      subNode.items.push(item);
    }
  }

  const ordered = [...serviceNodes.values()].sort(
    (a, b) =>
      a.service.sort_order - b.service.sort_order || a.service.id - b.service.id
  );
  for (const sn of ordered) {
    sn.categories.sort((a, b) => a.category.id - b.category.id);
    for (const cn of sn.categories) {
      cn.subcategories.sort(
        (a, b) => a.subcategory.id - b.subcategory.id
      );
    }
  }
  return ordered;
}

function smoothScrollTo(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  const top = el.getBoundingClientRect().top + window.scrollY - SCROLL_OFFSET;
  window.scrollTo({ top, behavior: "smooth" });
}

export default function StoreDetailPage({ params }: Props) {
  const t = useTranslations("StoreDetail");
  const { id } = use(params);
  const storeId = parseInt(id, 10);

  const [store, setStore] = useState<Store | null>(null);
  const [inventory, setInventory] = useState<InventoryWithProduct[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [subcategories, setSubcategories] = useState<Subcategory[]>([]);
  const [fetching, setFetching] = useState(true);
  const [activeServiceId, setActiveServiceId] = useState<number | null>(null);
  const [activeCategoryId, setActiveCategoryId] = useState<number | null>(null);
  const [subcategoryFilters, setSubcategoryFilters] = useState<
    Record<number, number | null>
  >({});

  useEffect(() => {
    Promise.all([
      get<Store>(`/api/v1/stores/${storeId}`),
      get<StoreInventory[]>(`/api/v1/stores/${storeId}/inventory`),
      get<MasterProduct[]>("/api/v1/catalog/products"),
      get<Service[]>("/api/v1/catalog/services"),
      get<Category[]>("/api/v1/catalog/categories"),
      get<Subcategory[]>("/api/v1/catalog/subcategories").catch(
        () => [] as Subcategory[]
      ),
    ])
      .then(([storeData, invData, products, svcs, cats, subs]) => {
        setStore(storeData);
        setServices(svcs);
        setCategories(cats);
        setSubcategories(subs);
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
  }, [storeId]);

  const tree = useMemo(
    () => buildTree(inventory, services, categories, subcategories),
    [inventory, services, categories, subcategories]
  );

  const activeServiceNode = useMemo(
    () => tree.find((n) => n.service.id === activeServiceId) ?? tree[0] ?? null,
    [tree, activeServiceId]
  );

  // Sidebar items derive from active service's categories.
  const sidebarItems = useMemo(() => {
    if (!activeServiceNode) return [];
    return activeServiceNode.categories.map((cn) => ({
      id: cn.category.id,
      icon: categoryGlyph(cn.category.name, activeServiceNode.service.slug),
      label: cn.category.name,
    }));
  }, [activeServiceNode]);

  const handleSidebarSelect = useCallback((catId: string | number) => {
    const idNum = typeof catId === "number" ? catId : parseInt(String(catId), 10);
    setActiveCategoryId(idNum);
    smoothScrollTo(CATEGORY_ANCHOR(idNum));
  }, []);

  const handleSubcategoryChange = useCallback(
    (categoryId: number, subcategoryId: number | null) => {
      setSubcategoryFilters((prev) => ({ ...prev, [categoryId]: subcategoryId }));
    },
    []
  );

  // Track scroll-spy active category.
  useEffect(() => {
    if (!activeServiceNode || activeServiceNode.categories.length === 0) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length > 0) {
          const id = visible[0].target.id;
          if (id.startsWith("category-")) {
            setActiveCategoryId(parseInt(id.slice("category-".length), 10));
          }
        }
      },
      { rootMargin: `-${SCROLL_OFFSET}px 0px -55% 0px`, threshold: 0 }
    );
    for (const cn of activeServiceNode.categories) {
      const el = document.getElementById(CATEGORY_ANCHOR(cn.category.id));
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [activeServiceNode]);

  if (fetching) {
    return (
      <div className={styles.page}>
        <div className={styles.shell}>
          <div className={styles.content}>
            <div className={`${styles.storeHeader} ${styles.skeletonHeader}`}>
              <div className={styles.storeHeaderLeft}>
                <div className={`${styles.storeIcon} ${styles.skeletonShape}`} />
                <div className={styles.storeInfo}>
                  <div className={`${styles.skeletonLine} ${styles.skeletonLineLg}`} />
                  <div className={styles.skeletonLine} />
                </div>
              </div>
            </div>
            <div className={styles.skeletonNav}>
              <div className={styles.skeletonPill} />
              <div className={styles.skeletonPill} />
              <div className={styles.skeletonPill} />
            </div>
            <div className={styles.productsGrid}>
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className={styles.skeletonCard} />
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!store) {
    return (
      <div className={styles.page}>
        <div className={styles.shell}>
          <div className={styles.content}>
            <div className={styles.notFound}>
              <div className={styles.notFoundIcon}>🔍</div>
              <h1 className={styles.notFoundTitle}>{t("notFoundTitle")}</h1>
              <p className={styles.notFoundText}>{t("notFoundBody")}</p>
              <Link href="/stores" className="btn btn-primary">
                {t("browseAllStores")}
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.shell}>
        <CategorySidebar
          items={sidebarItems}
          activeId={activeCategoryId}
          onSelect={handleSidebarSelect}
        />

        <div className={styles.content}>
          <header className={styles.storeHeader}>
            <div className={styles.storeHeaderLeft}>
              <div className={styles.storeIcon} aria-hidden="true">
                {store.name.charAt(0).toUpperCase()}
              </div>
              <div className={styles.storeInfo}>
                <h1 className={styles.storeName}>{store.name}</h1>
                <p className={styles.storeAddress}>{formatAddress(store.address)}</p>
              </div>
            </div>
            <div className={styles.statusBadge}>
              <span className={styles.statusDot} aria-hidden="true" />
              {t("openNow")}
            </div>
          </header>

          {tree.length === 0 ? (
            <div className={styles.empty}>
              <div className={styles.emptyIcon} aria-hidden="true">🛒</div>
              <p className={styles.emptyText}>{t("noProductsYet")}</p>
            </div>
          ) : (
            <>
              {tree.length > 1 && (
                <nav className={styles.serviceTabs} aria-label={t("navAriaLabel")}>
                  {tree.map((sn) => (
                    <button
                      key={sn.service.id}
                      type="button"
                      className={`${styles.servicePill} ${
                        sn.service.id === activeServiceId ? styles.servicePillActive : ""
                      }`}
                      onClick={() => {
                        setActiveServiceId(sn.service.id);
                        setActiveCategoryId(sn.categories[0]?.category.id ?? null);
                      }}
                      aria-current={sn.service.id === activeServiceId ? "true" : undefined}
                    >
                      {sn.service.name}
                      <span className={styles.servicePillCount}>{sn.totalItems}</span>
                    </button>
                  ))}
                </nav>
              )}

              {activeServiceNode && (
                <div>
                  {activeServiceNode.categories.map((cn) => (
                    <CategorySection
                      key={cn.category.id}
                      node={cn}
                      store={store}
                      service={activeServiceNode.service}
                      activeSubcategoryId={subcategoryFilters[cn.category.id] ?? null}
                      onSubcategoryChange={handleSubcategoryChange}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        <CartRail
          storeId={store.id}
          serviceId={activeServiceNode?.service.id}
        />
      </div>
    </div>
  );
}

interface CategorySectionProps {
  node: CategoryNode;
  store: Store;
  service: Service;
  activeSubcategoryId: number | null;
  onSubcategoryChange: (categoryId: number, subcategoryId: number | null) => void;
}

function CategorySection({
  node,
  store,
  service,
  activeSubcategoryId,
  onSubcategoryChange,
}: CategorySectionProps) {
  const t = useTranslations("StoreDetail");
  const activeSubName = useMemo(() => {
    if (activeSubcategoryId == null) return null;
    return (
      node.subcategories.find((s) => s.subcategory.id === activeSubcategoryId)
        ?.subcategory.name ?? null
    );
  }, [activeSubcategoryId, node.subcategories]);

  const items = useMemo(() => {
    if (activeSubcategoryId === null) return node.items;
    return node.items.filter((i) => i.product.subcategory_id === activeSubcategoryId);
  }, [activeSubcategoryId, node.items]);

  return (
    <section
      id={CATEGORY_ANCHOR(node.category.id)}
      className={styles.categorySection}
    >
      <div className={styles.categoryHeader}>
        <div className={styles.categoryHeadingWrap}>
          <h3 className={styles.categoryHeading}>{node.category.name}</h3>
          {activeSubName && (
            <span className={styles.activeFilterTag}>· {activeSubName}</span>
          )}
        </div>
        <span className={styles.categoryCount}>
          {t("categoryCount", { shown: items.length, total: node.items.length })}
        </span>
      </div>

      {node.subcategories.length > 1 && (
        <div
          className={styles.inlineSubcategories}
          role="tablist"
          aria-label={t("subcategoriesAriaLabel", { name: node.category.name })}
        >
          <button
            type="button"
            role="tab"
            className={`${styles.subChip} ${
              activeSubcategoryId === null ? styles.subChipActive : ""
            }`}
            aria-selected={activeSubcategoryId === null}
            onClick={() => onSubcategoryChange(node.category.id, null)}
          >
            {t("subAll")}
            <span className={styles.subChipCount}>{node.items.length}</span>
          </button>
          {node.subcategories.map((sn) => (
            <button
              key={sn.subcategory.id}
              type="button"
              role="tab"
              className={`${styles.subChip} ${
                activeSubcategoryId === sn.subcategory.id ? styles.subChipActive : ""
              }`}
              aria-selected={activeSubcategoryId === sn.subcategory.id}
              onClick={() => onSubcategoryChange(node.category.id, sn.subcategory.id)}
            >
              {sn.subcategory.name}
              <span className={styles.subChipCount}>{sn.items.length}</span>
            </button>
          ))}
        </div>
      )}

      {items.length > 0 ? (
        <div className={styles.productsGrid}>
          {items.map((item) => (
            <ProductCard
              key={item.id}
              item={item}
              storeId={store.id}
              storeName={store.name}
              serviceId={service.id}
              serviceName={service.name}
            />
          ))}
        </div>
      ) : (
        <div className={styles.emptyInline}>{t("noFilterMatch")}</div>
      )}
    </section>
  );
}
