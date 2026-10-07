"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState, use } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { compareProduct, type CompareResponse } from "@/lib/searchClient";
import { ProductOfferList } from "@/components/search/ProductOfferList";
import ProductGallery from "@/components/ProductDetail/ProductGallery";
import styles from "./page.module.css";

type Params = { productId: string; locale: string };

export default function ComparePage({ params }: { params: Promise<Params> }) {
  const { productId } = use(params);
  const t = useTranslations("Search");
  const locale = useLocale();
  const { location } = useDeliveryLocation();
  // Keyed by the location it was fetched for, so offers (and their courier
  // badges) for a previous location never show after the location changes.
  const [result, setResult] = useState<{ key: string; data: CompareResponse } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const locationKey = `${location?.lat},${location?.lng}`;
  const data = result?.key === locationKey ? result.data : null;

  useEffect(() => {
    let cancel = false;
    compareProduct(Number(productId), {
      lat: location?.lat,
      lng: location?.lng,
      locale,
    })
      .then((res) => {
        if (!cancel) setResult({ key: `${location?.lat},${location?.lng}`, data: res });
      })
      .catch(() => {
        if (!cancel) setError(t("unavailable"));
      });
    return () => {
      cancel = true;
    };
  }, [productId, location, locale, t]);

  if (error) return <main className={styles.page}>{error}</main>;
  if (!data) return <main className={styles.page}>{t("loading")}</main>;

  return (
    <main className={styles.page}>
      <div className={styles.hero}>
        <div className={styles.galleryCol}>
          <ProductGallery
            images={data.product.images ?? []}
            imageUrl={data.product.image_url ?? undefined}
            productName={data.product.name}
            variant="page"
          />
        </div>
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
