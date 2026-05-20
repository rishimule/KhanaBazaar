"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { get } from "@/lib/api";
import { formatAddress } from "@/lib/format-address";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { prefetchStorefront } from "@/lib/storefrontCache";
import { Service, Store } from "@/types";
import styles from "./page.module.css";

const PAGE_SIZE = 12;

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
  const [skip, setSkip] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const requestIdRef = useRef(0);
  const { location } = useDeliveryLocation();

  const fetchPage = useCallback(
    async (skipValue: number, append: boolean): Promise<void> => {
      const requestId = ++requestIdRef.current;
      if (append) {
        setLoadingMore(true);
      } else {
        setFetching(true);
      }

      const params = new URLSearchParams();
      if (location) {
        params.set("lat", String(location.lat));
        params.set("lng", String(location.lng));
        params.set("sort", "distance");
      }
      if (serviceSlug) {
        params.set("service", serviceSlug);
      }
      params.set("skip", String(skipValue));
      params.set("limit", String(PAGE_SIZE + 1));
      const url = `/api/v1/stores/?${params.toString()}`;

      try {
        const result = await get<Store[]>(url);
        if (requestIdRef.current !== requestId) return;
        const nextHasMore = result.length > PAGE_SIZE;
        const trimmed = nextHasMore ? result.slice(0, PAGE_SIZE) : result;
        if (append) {
          setStores((prev) => [...prev, ...trimmed]);
        } else {
          setStores(trimmed);
        }
        setSkip(skipValue + trimmed.length);
        setHasMore(nextHasMore);
      } catch {
        if (requestIdRef.current !== requestId) return;
        if (!append) {
          setStores([]);
          setHasMore(false);
        }
      } finally {
        if (requestIdRef.current === requestId) {
          if (append) {
            setLoadingMore(false);
          } else {
            setFetching(false);
          }
        }
      }
    },
    [location, serviceSlug],
  );

  useEffect(() => {
    fetchPage(0, false);
  }, [fetchPage]);

  useEffect(() => {
    if (!serviceSlug) return;
    get<Service[]>("/api/v1/catalog/services")
      .then(setServices)
      .catch(() => setServices([]));
  }, [serviceSlug, locale]);

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
            <div
              className={styles.filteredChip}
              role="status"
              aria-live="polite"
            >
              <span className={styles.filteredChipLabel}>
                {t("filteredHeader", { service: activeServiceName })}
              </span>
              <Link
                href="/stores"
                className={styles.filteredChipClear}
                aria-label={t("clearFilterAria", { service: activeServiceName })}
              >
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
                ? t("emptyAllWithLocation")
                : t("emptyAllNoLocation")}
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

        {hasMore && stores.length > 0 && (
          <div className={styles.loadMoreWrap}>
            <button
              type="button"
              className={`btn btn-primary ${styles.loadMoreBtn}`}
              onClick={() => fetchPage(skip, true)}
              disabled={loadingMore}
            >
              {loadingMore ? t("loadingMore") : t("loadMore")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
