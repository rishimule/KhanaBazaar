"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState, use } from "react";
import { useTranslations } from "next-intl";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { compareProduct, type CompareResponse } from "@/lib/searchClient";
import { ProductOfferList } from "@/components/search/ProductOfferList";
import styles from "./page.module.css";

type Params = { productId: string; locale: string };

export default function ComparePage({ params }: { params: Promise<Params> }) {
  const { productId } = use(params);
  const t = useTranslations("Search");
  const { location } = useDeliveryLocation();
  const [data, setData] = useState<CompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancel = false;
    compareProduct(Number(productId), {
      lat: location?.lat,
      lng: location?.lng,
    })
      .then((res) => {
        if (!cancel) setData(res);
      })
      .catch(() => {
        if (!cancel) setError(t("unavailable"));
      });
    return () => {
      cancel = true;
    };
  }, [productId, location, t]);

  if (error) return <main className={styles.page}>{error}</main>;
  if (!data) return <main className={styles.page}>{t("loading")}</main>;

  return (
    <main className={styles.page}>
      <div className={styles.hero}>
        {data.product.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={data.product.image_url}
            alt={data.product.name}
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            className={styles.heroImg}
          />
        ) : (
          <div aria-hidden className={styles.heroFallback}>
            🛒
          </div>
        )}
        <div>
          <h1 className={styles.title}>{data.product.name}</h1>
          {data.product.brand && (
            <div className={styles.brand}>{data.product.brand}</div>
          )}
          {data.product.unit && (
            <div className={styles.unit}>{data.product.unit}</div>
          )}
        </div>
      </div>
      <ProductOfferList data={data} />
    </main>
  );
}
