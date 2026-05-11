"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { get } from "@/lib/api";
import { formatAddress } from "@/lib/format-address";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { prefetchStorefront } from "@/lib/storefrontCache";
import { Store } from "@/types";
import styles from "./page.module.css";

export default function StoresPage() {
  const t = useTranslations("Stores");
  const locale = useLocale();
  const [stores, setStores] = useState<Store[]>([]);
  const [fetching, setFetching] = useState(true);
  const { location } = useDeliveryLocation();

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- show spinner while refetching after location change
    setFetching(true);
    const url = location
      ? `/api/v1/stores/?lat=${location.lat}&lng=${location.lng}&sort=distance`
      : "/api/v1/stores/";
    get<Store[]>(url)
      .then(setStores)
      .catch(() => setStores([]))
      .finally(() => setFetching(false));
  }, [location]);

  if (fetching) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <div className={styles.header}>
            <h1 className={styles.title}>{t("loading")}</h1>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.pageInner}>
        <div className={styles.header}>
          <h1 className={styles.title}>{t("browse")} {t("stores")}</h1>
          <p className={styles.subtitle}>{t("subtitle")}</p>
        </div>

        {location && stores.length === 0 && (
          <p className={styles.subtitle} style={{ textAlign: "center", padding: "32px 0" }}>
            No stores deliver to your selected location yet.
          </p>
        )}

        <div className={styles.grid}>
          {stores.map((store) => (
            <Link
              key={store.id}
              href={`/stores/${store.id}`}
              className={styles.card}
              id={`store-card-${store.id}`}
              // Warm the storefront cache the moment the user signals
              // intent to open the store. By the time they click, the
              // detail page paints synchronously from cache.
              onMouseEnter={() => prefetchStorefront(store.id, locale)}
              onFocus={() => prefetchStorefront(store.id, locale)}
              onTouchStart={() => prefetchStorefront(store.id, locale)}
            >
              <div className={styles.cardTop}>
                <span className={styles.cardIcon}>{store.name.charAt(0).toUpperCase()}</span>
                <span className={styles.cardStatus}>{t("openDot")}</span>
              </div>
              <div className={styles.cardBody}>
                <h2 className={styles.cardName}>{store.name}</h2>
                <p className={styles.cardAddress}>{formatAddress(store.address)}</p>
                <div className={styles.cardMeta}>
                  {typeof store.distance_km === "number" && (
                    <span className={styles.cardDistance}>
                      {store.distance_km.toFixed(1)} km away
                    </span>
                  )}
                </div>
                <span className={styles.viewBtn}>{t("viewStore")} →</span>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
