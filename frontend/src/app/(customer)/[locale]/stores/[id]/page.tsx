"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { use, useState, useMemo, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useTranslations, useLocale } from "next-intl";
import { formatAddress } from "@/lib/format-address";
import {
  Store,
  InventoryWithProduct,
  StorefrontCategory,
  StorefrontResponse,
  StorefrontService,
  StorefrontSubcategory,
} from "@/types";
import {
  loadStorefront,
  readCachedStorefront,
  readStaleStorefront,
} from "@/lib/storefrontCache";
import ProductCard from "@/components/ProductCard";
import CategorySidebar from "@/components/CategorySidebar";
import CartRail from "@/components/CartRail";
import styles from "./page.module.css";

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
  "meat-seafood": "🥩",
  beauty: "💄",
  stationery: "📚",
  "pet-supplies": "🐾",
  "home-kitchen": "🏠",
  "flowers-plants": "🌸",
  "sports-fitness": "🏋️",
};

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

function smoothScrollTo(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  const top = el.getBoundingClientRect().top + window.scrollY - SCROLL_OFFSET;
  window.scrollTo({ top, behavior: "smooth" });
}

/** Sum of items across all subcategories in a category. */
function categoryItemCount(cat: StorefrontCategory): number {
  let n = 0;
  for (const sub of cat.subcategories) n += sub.items.length;
  return n;
}

/** Sum across the whole service tree. */
function serviceItemCount(svc: StorefrontService): number {
  let n = 0;
  for (const cat of svc.categories) n += categoryItemCount(cat);
  return n;
}

export default function StoreDetailPage({ params }: Props) {
  const t = useTranslations("StoreDetail");
  const locale = useLocale();
  const { id } = use(params);
  const storeId = parseInt(id, 10);

  const [storefront, setStorefront] = useState<StorefrontResponse | null>(
    () => readStaleStorefront(storeId, locale),
  );
  const [fetching, setFetching] = useState(
    () => readCachedStorefront(storeId, locale) === null,
  );
  const [notFound, setNotFound] = useState(false);
  const [activeServiceId, setActiveServiceId] = useState<number | null>(null);
  const [activeCategoryId, setActiveCategoryId] = useState<number | null>(null);
  const [subcategoryFilters, setSubcategoryFilters] = useState<
    Record<number, number | null>
  >({});
  const [requestedMissingServiceId, setRequestedMissingServiceId] = useState<
    number | null
  >(null);
  const router = useRouter();
  const searchParams = useSearchParams();
  const seedRef = useRef(false);

  // Stale-while-revalidate: render cached data immediately if available
  // (handled by the useState lazy initialiser above), then refresh in
  // the background. The fresh-cache fast path is intentionally a no-op
  // in this effect — the initial render already carries the cached
  // value, so we only do work when the cache is empty or stale.
  useEffect(() => {
    if (readCachedStorefront(storeId, locale)) return;

    let cancelled = false;
    loadStorefront(storeId, locale)
      .then((data) => {
        if (cancelled) return;
        setStorefront(data);
        setNotFound(false);
      })
      .catch(() => {
        if (!cancelled) setNotFound(true);
      })
      .finally(() => {
        if (!cancelled) setFetching(false);
      });
    return () => {
      cancelled = true;
    };
  }, [storeId, locale]);

  const services = useMemo(
    () => storefront?.services ?? [],
    [storefront],
  );
  const store = storefront?.store ?? null;

  useEffect(() => {
    if (seedRef.current) return;
    if (!storefront) return;
    const raw = searchParams.get("service");
    if (raw === null) {
      seedRef.current = true;
      return;
    }
    const parsed = parseInt(raw, 10);
    seedRef.current = true;
    if (!Number.isFinite(parsed)) {
      router.replace(`/stores/${storeId}`, { scroll: false });
      return;
    }
    const inStorefront =
      storefront.services.find((s) => s.id === parsed) ?? null;
    const inStore =
      storefront.store.services.find((s) => s.id === parsed) ?? null;
    if (inStorefront) {
      setActiveServiceId(inStorefront.id);
      setActiveCategoryId(inStorefront.categories[0]?.id ?? null);
    } else if (inStore) {
      setRequestedMissingServiceId(parsed);
    }
    router.replace(`/stores/${storeId}`, { scroll: false });
  }, [storefront, searchParams, router, storeId]);

  const activeServiceNode = useMemo(() => {
    if (requestedMissingServiceId !== null) return null;
    return services.find((s) => s.id === activeServiceId) ?? services[0] ?? null;
  }, [services, activeServiceId, requestedMissingServiceId]);

  const sidebarItems = useMemo(() => {
    if (!activeServiceNode) return [];
    return activeServiceNode.categories.map((cat) => ({
      id: cat.id,
      icon: categoryGlyph(cat.name, activeServiceNode.slug),
      label: cat.name,
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
    [],
  );

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
      { rootMargin: `-${SCROLL_OFFSET}px 0px -55% 0px`, threshold: 0 },
    );
    for (const cat of activeServiceNode.categories) {
      const el = document.getElementById(CATEGORY_ANCHOR(cat.id));
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [activeServiceNode]);

  if (fetching && !storefront) {
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

  if (notFound || !store) {
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

          {requestedMissingServiceId !== null ? (
            <div className={styles.empty}>
              <div className={styles.emptyIcon} aria-hidden="true">🛒</div>
              <p className={styles.emptyText}>
                {t("noProductsForService", {
                  service:
                    store.services.find(
                      (s) => s.id === requestedMissingServiceId,
                    )?.name ?? "",
                })}
              </p>
            </div>
          ) : services.length === 0 ? (
            <div className={styles.empty}>
              <div className={styles.emptyIcon} aria-hidden="true">🛒</div>
              <p className={styles.emptyText}>{t("noProductsYet")}</p>
            </div>
          ) : (
            <>
              {services.length > 1 && (
                <nav className={styles.serviceTabs} aria-label={t("navAriaLabel")}>
                  {services.map((svc) => (
                    <button
                      key={svc.id}
                      type="button"
                      className={`${styles.servicePill} ${
                        svc.id === (activeServiceNode?.id ?? null)
                          ? styles.servicePillActive
                          : ""
                      }`}
                      onClick={() => {
                        setActiveServiceId(svc.id);
                        setActiveCategoryId(svc.categories[0]?.id ?? null);
                      }}
                      aria-current={
                        svc.id === (activeServiceNode?.id ?? null) ? "true" : undefined
                      }
                    >
                      {svc.name}
                      <span className={styles.servicePillCount}>
                        {serviceItemCount(svc)}
                      </span>
                    </button>
                  ))}
                </nav>
              )}

              {activeServiceNode && (
                <div>
                  {activeServiceNode.categories.map((cat) => (
                    <CategorySection
                      key={cat.id}
                      store={store}
                      service={activeServiceNode}
                      category={cat}
                      activeSubcategoryId={subcategoryFilters[cat.id] ?? null}
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
          serviceId={activeServiceNode?.id}
        />
      </div>
    </div>
  );
}

interface CategorySectionProps {
  store: Store;
  service: StorefrontService;
  category: StorefrontCategory;
  activeSubcategoryId: number | null;
  onSubcategoryChange: (categoryId: number, subcategoryId: number | null) => void;
}

function CategorySection({
  store,
  service,
  category,
  activeSubcategoryId,
  onSubcategoryChange,
}: CategorySectionProps) {
  const t = useTranslations("StoreDetail");

  const totalItems = useMemo(() => categoryItemCount(category), [category]);

  const activeSubName = useMemo(() => {
    if (activeSubcategoryId == null) return null;
    return (
      category.subcategories.find((s) => s.id === activeSubcategoryId)?.name ?? null
    );
  }, [activeSubcategoryId, category.subcategories]);

  const visibleSubs: StorefrontSubcategory[] = useMemo(() => {
    if (activeSubcategoryId === null) return category.subcategories;
    const match = category.subcategories.find((s) => s.id === activeSubcategoryId);
    return match ? [match] : [];
  }, [activeSubcategoryId, category.subcategories]);

  const shownCount = useMemo(() => {
    let n = 0;
    for (const sub of visibleSubs) n += sub.items.length;
    return n;
  }, [visibleSubs]);

  return (
    <section
      id={CATEGORY_ANCHOR(category.id)}
      className={styles.categorySection}
    >
      <div className={styles.categoryHeader}>
        <div className={styles.categoryHeadingWrap}>
          <h3 className={styles.categoryHeading}>{category.name}</h3>
          {activeSubName && (
            <span className={styles.activeFilterTag}>· {activeSubName}</span>
          )}
        </div>
        <span className={styles.categoryCount}>
          {t("categoryCount", { shown: shownCount, total: totalItems })}
        </span>
      </div>

      {category.subcategories.length > 1 && (
        <div
          className={styles.inlineSubcategories}
          role="tablist"
          aria-label={t("subcategoriesAriaLabel", { name: category.name })}
        >
          <button
            type="button"
            role="tab"
            className={`${styles.subChip} ${
              activeSubcategoryId === null ? styles.subChipActive : ""
            }`}
            aria-selected={activeSubcategoryId === null}
            onClick={() => onSubcategoryChange(category.id, null)}
          >
            {t("subAll")}
            <span className={styles.subChipCount}>{totalItems}</span>
          </button>
          {category.subcategories.map((sub) => (
            <button
              key={sub.id}
              type="button"
              role="tab"
              className={`${styles.subChip} ${
                activeSubcategoryId === sub.id ? styles.subChipActive : ""
              }`}
              aria-selected={activeSubcategoryId === sub.id}
              onClick={() => onSubcategoryChange(category.id, sub.id)}
            >
              {sub.name}
              <span className={styles.subChipCount}>{sub.items.length}</span>
            </button>
          ))}
        </div>
      )}

      {shownCount > 0 ? (
        <div className={styles.productsGrid}>
          {visibleSubs.flatMap((sub) =>
            sub.items.map((item) => {
              // ProductCard was written against `InventoryWithProduct`
              // (flat catalog era). Adapt the storefront tree node to
              // that shape here so the card and its cart wiring stay
              // unchanged.
              const adapted: InventoryWithProduct = {
                id: item.inventory_id,
                store_id: store.id,
                product_id: item.product_id,
                price: item.price,
                stock: item.stock,
                is_available: item.stock > 0,
                created_at: "",
                updated_at: "",
                product: {
                  id: item.product_id,
                  name: item.product_name,
                  description: item.description ?? "",
                  image_url: item.image_url ?? "",
                  category_id: category.id,
                  subcategory_id: sub.id,
                  subcategory_name: sub.name,
                  base_price: item.price,
                  created_at: "",
                  updated_at: "",
                },
              };
              return (
                <ProductCard
                  key={item.inventory_id}
                  item={adapted}
                  storeId={store.id}
                  storeName={store.name}
                  serviceId={service.id}
                  serviceName={service.name}
                />
              );
            }),
          )}
        </div>
      ) : (
        <div className={styles.emptyInline}>{t("noFilterMatch")}</div>
      )}
    </section>
  );
}
