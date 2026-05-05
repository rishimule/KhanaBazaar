"use client";

import { use, useState, useMemo, useEffect, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
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

const SERVICE_ANCHOR = (id: number) => `service-${id}`;
const CATEGORY_ANCHOR = (id: number) => `category-${id}`;
const SCROLL_OFFSET = 180;

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
  const { id } = use(params);
  const storeId = parseInt(id, 10);
  const router = useRouter();
  const { dbUser, loading: authLoading } = useAuth();

  const [store, setStore] = useState<Store | null>(null);
  const [inventory, setInventory] = useState<InventoryWithProduct[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [subcategories, setSubcategories] = useState<Subcategory[]>([]);
  const [fetching, setFetching] = useState(true);
  const [activeAnchor, setActiveAnchor] = useState<string | null>(null);
  const [subcategoryFilters, setSubcategoryFilters] = useState<
    Record<number, number | null>
  >({});

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
    }
  }, [authLoading, dbUser, storeId, router]);

  const tree = useMemo(
    () => buildTree(inventory, services, categories, subcategories),
    [inventory, services, categories, subcategories]
  );

  const onlyOneService = tree.length === 1;

  const handleServiceClick = useCallback((serviceId: number) => {
    smoothScrollTo(SERVICE_ANCHOR(serviceId));
  }, []);

  const handleCategoryClick = useCallback((categoryId: number) => {
    smoothScrollTo(CATEGORY_ANCHOR(categoryId));
  }, []);

  const handleSubcategoryChange = useCallback(
    (categoryId: number, subcategoryId: number | null) => {
      setSubcategoryFilters((prev) => ({ ...prev, [categoryId]: subcategoryId }));
    },
    []
  );

  useEffect(() => {
    if (tree.length === 0) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length > 0) {
          setActiveAnchor(visible[0].target.id);
        }
      },
      { rootMargin: `-${SCROLL_OFFSET}px 0px -55% 0px`, threshold: 0 }
    );
    const ids: string[] = [];
    for (const sn of tree) {
      ids.push(SERVICE_ANCHOR(sn.service.id));
      for (const cn of sn.categories) ids.push(CATEGORY_ANCHOR(cn.category.id));
    }
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [tree]);

  let activeServiceId: number | null = null;
  let activeCategoryId: number | null = null;
  if (tree.length > 0) {
    if (activeAnchor?.startsWith("category-")) {
      const cid = parseInt(activeAnchor.slice("category-".length), 10);
      for (const sn of tree) {
        const cn = sn.categories.find((c) => c.category.id === cid);
        if (cn) {
          activeServiceId = sn.service.id;
          activeCategoryId = cid;
          break;
        }
      }
    } else if (activeAnchor?.startsWith("service-")) {
      const sid = parseInt(activeAnchor.slice("service-".length), 10);
      const sn = tree.find((s) => s.service.id === sid);
      if (sn) {
        activeServiceId = sid;
        activeCategoryId = sn.categories[0]?.category.id ?? null;
      }
    }
    if (activeServiceId == null) {
      activeServiceId = tree[0].service.id;
      activeCategoryId = tree[0].categories[0]?.category.id ?? null;
    }
  }

  if (authLoading || fetching) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <StoreHeaderSkeleton />
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

  return (
    <div className={styles.page}>
      <div className={styles.pageInner}>
        <header className={styles.storeHeader}>
          <div className={styles.storeHeaderLeft}>
            <div className={styles.storeIcon} aria-hidden="true">🏪</div>
            <div className={styles.storeInfo}>
              <h1 className={styles.storeName}>{store.name}</h1>
              <p className={styles.storeAddress}>{formatAddress(store.address)}</p>
            </div>
          </div>
          <div className={styles.statusBadge}>
            <span className={styles.statusDot} aria-hidden="true" />
            Open Now
          </div>
        </header>

        {tree.length === 0 ? (
          <div className={styles.empty}>
            <div className={styles.emptyIcon} aria-hidden="true">🛒</div>
            <p className={styles.emptyText}>This store has no products yet.</p>
          </div>
        ) : (
          <>
            <StoreNav
              tree={tree}
              activeServiceId={activeServiceId}
              onServiceClick={handleServiceClick}
              hideServiceRow={onlyOneService}
            />
            <div className={styles.shelves}>
              {tree.map((sn) => (
                <ServiceShelf
                  key={sn.service.id}
                  node={sn}
                  store={store}
                  hideServiceHeading={onlyOneService}
                  subcategoryFilters={subcategoryFilters}
                  activeCategoryId={activeCategoryId}
                  onSubcategoryChange={handleSubcategoryChange}
                  onCategoryClick={handleCategoryClick}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

interface StoreNavProps {
  tree: ServiceNode[];
  activeServiceId: number | null;
  onServiceClick: (id: number) => void;
  hideServiceRow: boolean;
}

function StoreNav({
  tree,
  activeServiceId,
  onServiceClick,
  hideServiceRow,
}: StoreNavProps) {
  if (hideServiceRow || tree.length <= 1) return null;

  return (
    <nav className={styles.stickyNav} aria-label="Store sections">
      <div className={`${styles.navRow} ${styles.navRowServices}`}>
        {tree.map((sn) => (
          <button
            key={sn.service.id}
            type="button"
            className={`${styles.navPill} ${
              sn.service.id === activeServiceId ? styles.navPillActive : ""
            }`}
            onClick={() => onServiceClick(sn.service.id)}
            aria-current={sn.service.id === activeServiceId ? "true" : undefined}
          >
            {sn.service.name}
            <span className={styles.navCount}>{sn.totalItems}</span>
          </button>
        ))}
      </div>
    </nav>
  );
}

interface ServiceShelfProps {
  node: ServiceNode;
  store: Store;
  hideServiceHeading: boolean;
  subcategoryFilters: Record<number, number | null>;
  activeCategoryId: number | null;
  onSubcategoryChange: (categoryId: number, subcategoryId: number | null) => void;
  onCategoryClick: (categoryId: number) => void;
}

function ServiceShelf({
  node,
  store,
  hideServiceHeading,
  subcategoryFilters,
  activeCategoryId,
  onSubcategoryChange,
  onCategoryClick,
}: ServiceShelfProps) {
  return (
    <section
      id={SERVICE_ANCHOR(node.service.id)}
      className={styles.serviceShelf}
      aria-label={node.service.name}
    >
      {!hideServiceHeading && (
        <div className={styles.serviceHeader}>
          <h2 className={styles.serviceHeading}>{node.service.name}</h2>
          <span className={styles.serviceCount}>
            {node.totalItems} item{node.totalItems === 1 ? "" : "s"}
          </span>
        </div>
      )}
      {node.categories.length > 0 && (
        <div
          className={styles.inlineCategories}
          aria-label={`${node.service.name} categories`}
        >
          {node.categories.map((cn) => (
            <button
              key={cn.category.id}
              type="button"
              className={`${styles.navChip} ${
                cn.category.id === activeCategoryId ? styles.navChipActive : ""
              }`}
              onClick={() => onCategoryClick(cn.category.id)}
              aria-current={cn.category.id === activeCategoryId ? "true" : undefined}
            >
              {cn.category.name}
              <span className={styles.navChipCount}>{cn.items.length}</span>
            </button>
          ))}
        </div>
      )}
      {node.categories.map((cn) => (
        <CategorySection
          key={cn.category.id}
          node={cn}
          store={store}
          activeSubcategoryId={subcategoryFilters[cn.category.id] ?? null}
          onSubcategoryChange={onSubcategoryChange}
        />
      ))}
    </section>
  );
}

interface CategorySectionProps {
  node: CategoryNode;
  store: Store;
  activeSubcategoryId: number | null;
  onSubcategoryChange: (categoryId: number, subcategoryId: number | null) => void;
}

function CategorySection({
  node,
  store,
  activeSubcategoryId,
  onSubcategoryChange,
}: CategorySectionProps) {
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
          {items.length} of {node.items.length}
        </span>
      </div>

      {node.subcategories.length > 1 && (
        <div
          className={styles.inlineSubcategories}
          role="tablist"
          aria-label={`${node.category.name} subcategories`}
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
            All
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
            />
          ))}
        </div>
      ) : (
        <div className={styles.emptyInline}>
          No products match this filter.
        </div>
      )}
    </section>
  );
}

function StoreHeaderSkeleton() {
  return (
    <div className={`${styles.storeHeader} ${styles.skeletonHeader}`}>
      <div className={styles.storeHeaderLeft}>
        <div className={`${styles.storeIcon} ${styles.skeletonShape}`} />
        <div className={styles.storeInfo}>
          <div className={`${styles.skeletonLine} ${styles.skeletonLineLg}`} />
          <div className={styles.skeletonLine} />
        </div>
      </div>
    </div>
  );
}
