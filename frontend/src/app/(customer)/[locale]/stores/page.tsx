"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { get } from "@/lib/api";
import { formatAddress } from "@/lib/format-address";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { prefetchStorefront } from "@/lib/storefrontCache";
import { Service, Store } from "@/types";
import styles from "./page.module.css";

export default function StoresPage() {
  const t = useTranslations("Stores");
  return (
    <Suspense
      fallback={
        <div className={styles.page}>
          <div className={styles.pageInner}>
            <div className={styles.header}>
              <h1 className={styles.title}>{t("loading")}</h1>
            </div>
          </div>
        </div>
      }
    >
      <StoresPageInner />
    </Suspense>
  );
}

function StoresPageInner() {
  const t = useTranslations("Stores");
  const locale = useLocale();
  const searchParams = useSearchParams();
  const serviceSlug = searchParams.get("service");

  const [stores, setStores] = useState<Store[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [fetching, setFetching] = useState(true);
  const { location } = useDeliveryLocation();

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- show spinner while refetching after location/slug change
    setFetching(true);
    const params = new URLSearchParams();
    if (location) {
      params.set("lat", String(location.lat));
      params.set("lng", String(location.lng));
      params.set("sort", "distance");
    }
    if (serviceSlug) {
      params.set("service", serviceSlug);
    }
    const qs = params.toString();
    const url = `/api/v1/stores/${qs ? `?${qs}` : ""}`;
    get<Store[]>(url)
      .then(setStores)
      .catch(() => setStores([]))
      .finally(() => setFetching(false));
  }, [location, serviceSlug]);

  useEffect(() => {
    if (!serviceSlug) return;
    get<Service[]>("/api/v1/catalog/services")
      .then(setServices)
      .catch(() => setServices([]));
  }, [serviceSlug]);

  const activeService = useMemo(
    () => services.find((s) => s.slug === serviceSlug) ?? null,
    [services, serviceSlug],
  );
  const activeServiceName = activeService?.name ?? serviceSlug ?? "";

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
          {serviceSlug && (
            <div className={styles.filteredChip}>
              <span className={styles.filteredChipLabel}>
                {t("filteredHeader", { service: activeServiceName })}
              </span>
              <Link href="/stores" className={styles.filteredChipClear}>
                {t("clearFilter")}
              </Link>
            </div>
          )}
        </div>

        {stores.length === 0 && (
          <p
            className={styles.subtitle}
            style={{ textAlign: "center", padding: "32px 0" }}
          >
            {serviceSlug
              ? location
                ? t("emptyWithLocation", { service: activeServiceName })
                : t("emptyNoLocation", { service: activeServiceName })
              : location
                ? "No stores deliver to your selected location yet."
                : "No stores available."}
          </p>
        )}

        <div className={styles.grid}>
          {stores.map((store) => {
            const matchedService = serviceSlug
              ? store.services.find((s) => s.slug === serviceSlug)
              : null;
            const href = matchedService
              ? `/stores/${store.id}?service=${matchedService.id}`
              : `/stores/${store.id}`;
            return (
              <Link
                key={store.id}
                href={href}
                className={styles.card}
                id={`store-card-${store.id}`}
                onMouseEnter={() => prefetchStorefront(store.id, locale)}
                onFocus={() => prefetchStorefront(store.id, locale)}
                onTouchStart={() => prefetchStorefront(store.id, locale)}
              >
                <div className={styles.cardTop}>
                  <span className={styles.cardIcon}>
                    {store.name.charAt(0).toUpperCase()}
                  </span>
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
            );
          })}
        </div>
      </div>
    </div>
  );
}
