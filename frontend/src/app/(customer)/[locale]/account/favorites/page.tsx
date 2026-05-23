"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import ProductCard from "@/components/ProductCard";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import {
  isDefaultDeliveryLocation,
  useDeliveryLocation,
} from "@/lib/DeliveryLocationContext";
import { useFavorites } from "@/lib/FavoritesContext";
import type {
  FavoriteAtStore,
  FavoriteProductPreview,
  FavoritesGroupedResponse,
  InventoryWithProduct,
} from "@/types";
import styles from "./page.module.css";

function toInventoryItem(
  it: FavoriteAtStore,
  storeId: number,
): InventoryWithProduct {
  return {
    id: it.inventory_id,
    store_id: storeId,
    product_id: it.product_id,
    price: it.price,
    stock: it.stock,
    is_available: it.stock > 0,
    created_at: it.favourited_at,
    updated_at: it.favourited_at,
    product: {
      id: it.product_id,
      name: it.name,
      description: "",
      category_id: it.category_id,
      subcategory_id: 0,
      subcategory_name: "",
      image_url: it.image_url ?? undefined,
      base_price: it.price,
      created_at: it.favourited_at,
      updated_at: it.favourited_at,
    },
  };
}

export default function FavoritesPage() {
  const t = useTranslations("Favorites");
  const locale = useLocale();
  const { dbUser, token } = useAuth();
  const { location } = useDeliveryLocation();
  const { count: favCount } = useFavorites();
  const needsLocation = isDefaultDeliveryLocation(location);

  const [data, setData] = useState<FavoritesGroupedResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const isCustomer = dbUser?.role === "customer";

  const refetch = useCallback(() => setRefreshKey((k) => k + 1), []);

  useEffect(() => {
    if (!isCustomer || !token || needsLocation) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const res = await get<FavoritesGroupedResponse>(
          `/api/v1/favorites/?lat=${location.lat}&lng=${location.lng}`,
          token,
        );
        if (!cancelled) setData(res);
      } catch (e) {
        if (!cancelled) setError(t("errorRetry"));
        console.error(e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isCustomer, token, needsLocation, location.lat, location.lng, t, refreshKey]);

  if (needsLocation) {
    return (
      <section className={styles.banner}>
        <p>{t("setLocation")}</p>
        <Link href={`/${locale}/stores`} className="btn btn-primary">
          {t("browseStores")}
        </Link>
      </section>
    );
  }

  if (loading && !data) return <FavoritesSkeleton />;

  if (error) {
    return (
      <section className={styles.error}>
        <p>{error}</p>
        <button className="btn btn-secondary" onClick={refetch}>
          {t("errorRetry")}
        </button>
      </section>
    );
  }

  if (!data) return null;

  const total =
    data.groups.reduce((n, g) => n + g.items.length, 0) +
    data.unavailable.length;

  if (total === 0) {
    return <FavoritesEmpty locale={locale} />;
  }

  return (
    <>
      <header className={styles.header}>
        <h1>{t("title")}</h1>
        <p>
          {t("subtitle", {
            count: favCount || total,
            city: location.label || "—",
          })}
        </p>
      </header>

      {data.groups.map((g) => (
        <section key={g.store_id} className={styles.storeSection}>
          <header className={styles.storeHeader}>
            <Link href={`/${locale}/stores/${g.store_id}`}>
              <h2>{g.store_name}</h2>
            </Link>
            <span className={styles.distance}>
              {g.distance_km.toFixed(1)} km
            </span>
          </header>
          <div className={styles.grid}>
            {g.items.map((it) => (
              <ProductCard
                key={`${g.store_id}-${it.product_id}`}
                item={toInventoryItem(it, g.store_id)}
                storeId={g.store_id}
                storeName={g.store_name}
                serviceId={0}
                serviceName=""
              />
            ))}
          </div>
        </section>
      ))}

      {data.unavailable.length > 0 && (
        <details className={styles.unavailable}>
          <summary>
            {t("unavailableSection", { count: data.unavailable.length })}
          </summary>
          <div className={styles.unavailableGrid}>
            {data.unavailable.map((p) => (
              <UnavailableCard key={p.product_id} product={p} />
            ))}
          </div>
        </details>
      )}
    </>
  );
}

function FavoritesSkeleton() {
  return (
    <div className={styles.skeleton}>
      {[0, 1, 2].map((i) => (
        <div key={i} className={styles.skelStore}>
          <div className={styles.skelHeader} />
          <div className={styles.skelGrid}>
            {[0, 1, 2, 3].map((j) => (
              <div key={j} className={styles.skelCard} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function FavoritesEmpty({ locale }: { locale: string }) {
  const t = useTranslations("Favorites");
  return (
    <section className={styles.empty}>
      <svg
        viewBox="0 0 64 64"
        width="120"
        height="120"
        aria-hidden
        className={styles.heartIcon}
      >
        <path
          d="M48 12c-4 0-7 2-9 5l-7-9-7 9c-2-3-5-5-9-5C9 12 4 17 4 23c0 14 28 30 28 30s28-16 28-30c0-6-5-11-12-11z"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinejoin="round"
        />
      </svg>
      <h2>{t("emptyHeading")}</h2>
      <p>{t("emptyBody")}</p>
      <Link href={`/${locale}/stores`} className="btn btn-primary">
        {t("browseStores")}
      </Link>
    </section>
  );
}

function UnavailableCard({ product }: { product: FavoriteProductPreview }) {
  return (
    <div className={styles.unavailableCard}>
      {product.image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={product.image_url}
          alt={product.name}
          referrerPolicy="no-referrer"
        />
      ) : (
        <span aria-hidden>📦</span>
      )}
      <span>{product.name}</span>
    </div>
  );
}
