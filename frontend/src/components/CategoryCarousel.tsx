"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useRef, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { searchProducts, type BrowseCategory } from "@/lib/searchClient";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { ScrollRail } from "@/components/ScrollRail";
import { ProductMiniCard } from "@/components/ProductMiniCard";
import styles from "./CategoryCarousel.module.css";

type RowItem = {
  id: number;
  name: string;
  image_url: string | null;
  brand: string | null;
  min_price: number;
  max_price: number;
  in_stock_anywhere: boolean;
};

type Props = {
  category: BrowseCategory;
  serviceId: number;
  serviceSlug: string;
};

export function CategoryCarousel({ category, serviceId, serviceSlug }: Props) {
  const t = useTranslations("Products");
  const locale = useLocale();
  const { location } = useDeliveryLocation();

  const initial: RowItem[] = category.products.map((p) => ({
    id: p.id,
    name: p.name,
    image_url: p.image_url,
    brand: p.brand,
    min_price: p.min_price,
    max_price: p.max_price,
    in_stock_anywhere: p.in_stock_anywhere,
  }));

  const [activeSub, setActiveSub] = useState<number | null>(null);
  const [items, setItems] = useState<RowItem[]>(initial);
  const [loading, setLoading] = useState(false);
  // Cache fetched rows per subcategory so toggling back is instant.
  const cache = useRef<Map<number, RowItem[]>>(new Map());

  async function selectSub(subId: number | null) {
    setActiveSub(subId);
    if (subId === null) {
      setItems(initial);
      return;
    }
    const cached = cache.current.get(subId);
    if (cached) {
      setItems(cached);
      return;
    }
    setLoading(true);
    try {
      const res = await searchProducts(
        {
          q: "",
          serviceId,
          categoryId: category.id,
          subcategoryId: subId,
          lat: location?.lat,
          lng: location?.lng,
          pageSize: 20,
        },
        locale,
      );
      const mapped: RowItem[] = res.products.map((p) => ({
        id: p.id,
        name: p.name,
        image_url: p.image_url,
        brand: p.brand,
        min_price: p.min_price,
        max_price: p.max_price,
        in_stock_anywhere: p.in_stock_anywhere,
      }));
      cache.current.set(subId, mapped);
      setItems(mapped);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className={styles.carousel}>
      <div className={styles.head}>
        <h2 className={styles.title}>{category.name}</h2>
        <Link
          href={`/products?service=${encodeURIComponent(serviceSlug)}&category=${category.id}`}
          className={styles.seeAll}
        >
          {t("seeAll")} ›
        </Link>
      </div>

      {category.subcategories.length > 0 && (
        <div className={styles.chipRow}>
          <ScrollRail ariaLabel={`${category.name} ${t("seeAll")}`}>
            <button
              type="button"
              className={`${styles.chip} ${activeSub === null ? styles.chipActive : ""}`}
              onClick={() => selectSub(null)}
              aria-pressed={activeSub === null}
            >
              {t("allSubcategories")}
            </button>
            {category.subcategories.map((s) => (
              <button
                key={s.id}
                type="button"
                className={`${styles.chip} ${activeSub === s.id ? styles.chipActive : ""}`}
                onClick={() => selectSub(s.id)}
                aria-pressed={activeSub === s.id}
              >
                {s.name}
              </button>
            ))}
          </ScrollRail>
        </div>
      )}

      {loading ? (
        <div className={styles.rowMsg}>{t("loading")}</div>
      ) : items.length === 0 ? (
        <div className={styles.rowMsg}>{t("empty")}</div>
      ) : (
        <ScrollRail
          ariaLabel={category.name}
          leftLabel={t("scrollLeft")}
          rightLabel={t("scrollRight")}
        >
          {items.map((p) => (
            <div key={p.id} className={styles.railItem}>
              <ProductMiniCard
                href={`/${locale}/search/product/${p.id}`}
                name={p.name}
                imageUrl={p.image_url}
                brand={p.brand}
                minPrice={p.min_price}
                maxPrice={p.max_price}
                inStock={p.in_stock_anywhere}
                outOfStockLabel={t("empty")}
              />
            </div>
          ))}
        </ScrollRail>
      )}
    </section>
  );
}
