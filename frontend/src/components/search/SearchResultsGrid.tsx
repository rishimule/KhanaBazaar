"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { searchProducts, type ProductCard } from "@/lib/searchClient";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import styles from "./SearchResultsGrid.module.css";

type Props = {
  q: string;
  storeId?: number;
  serviceId?: number;
  categoryId?: number;
  minPrice?: number;
  maxPrice?: number;
  sort?: string;
};

export function SearchResultsGrid({
  q,
  storeId,
  serviceId,
  categoryId,
  minPrice,
  maxPrice,
  sort,
}: Props) {
  const locale = useLocale();
  const t = useTranslations("Search");
  const { location } = useDeliveryLocation();
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<ProductCard[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset on query/filter change.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset pagination when query/filters change
    setItems([]);
    setPage(1);
    setTotal(0);
    setError(null);
  }, [q, storeId, serviceId, categoryId, minPrice, maxPrice, sort]);

  useEffect(() => {
    let cancel = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- start loading state synchronously to render skeleton
    setLoading(true);
    setError(null);
    searchProducts({
      q,
      storeId,
      serviceId,
      categoryId,
      minPrice,
      maxPrice,
      sort,
      lat: location?.lat,
      lng: location?.lng,
      page,
      pageSize: 24,
    })
      .then((res) => {
        if (cancel) return;
        setItems((cur) => (page === 1 ? res.products : [...cur, ...res.products]));
        setTotal(res.total);
      })
      .catch(() => {
        if (!cancel) setError(t("unavailable"));
      })
      .finally(() => {
        if (!cancel) setLoading(false);
      });
    return () => {
      cancel = true;
    };
  }, [q, storeId, serviceId, categoryId, minPrice, maxPrice, sort, page, location, t]);

  if (error) {
    return <div className={styles.error}>{error}</div>;
  }

  if (!loading && items.length === 0) {
    return <div className={styles.empty}>{t("noResults", { q })}</div>;
  }

  return (
    <div>
      <div role="status" aria-live="polite" className={styles.sr}>
        {total} results
      </div>
      <div className={styles.grid}>
        {items.map((p) => (
          <Link
            key={p.id}
            href={`/${locale}/search/product/${p.id}`}
            className={styles.card}
          >
            {p.image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={p.image_url}
                alt={p.name}
                loading="lazy"
                decoding="async"
                referrerPolicy="no-referrer"
                className={styles.img}
              />
            ) : (
              <div aria-hidden className={styles.imgFallback}>
                🛒
              </div>
            )}
            <div className={styles.name}>{p.name}</div>
            {p.brand && <div className={styles.brand}>{p.brand}</div>}
            <div className={styles.price}>
              ₹{p.min_price.toFixed(0)}
              {p.max_price !== p.min_price && (
                <span className={styles.range}> – ₹{p.max_price.toFixed(0)}</span>
              )}
            </div>
            {!p.in_stock_anywhere && (
              <div className={styles.badge}>{t("outOfStock")}</div>
            )}
          </Link>
        ))}
      </div>
      {items.length < total && (
        <button
          type="button"
          className={styles.loadMore}
          onClick={() => setPage((n) => n + 1)}
          disabled={loading}
        >
          {loading ? t("loading") : t("loadMore")}
        </button>
      )}
    </div>
  );
}
