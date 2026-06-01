"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { get } from "@/lib/api";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { ScrollRail } from "@/components/ScrollRail";
import ProductCard from "@/components/ProductCard";
import { DeliveryLocationPicker } from "@/components/DeliveryLocationPicker";
import { InventoryWithProduct, Service, Store } from "@/types";
import styles from "./HomeStorePreview.module.css";

const MAX_CANDIDATES = 4;
const PREVIEW_LIMIT = 10;

export interface PreviewCandidate {
  store: Store;
  service: Service;
}

interface Resolved {
  store: Store;
  service: Service;
  items: InventoryWithProduct[];
}

export function HomeStorePreview({ candidates }: { candidates: PreviewCandidate[] }) {
  const t = useTranslations("Home");
  const { userSet, hydrated } = useDeliveryLocation();
  const [resolved, setResolved] = useState<Resolved | null>(null);
  const [loading, setLoading] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const list = candidates.slice(0, MAX_CANDIDATES);
    (async () => {
      if (list.length === 0) {
        if (!cancelled) {
          setResolved(null);
          setLoading(false);
        }
        return;
      }
      setLoading(true);
      setResolved(null);
      for (const c of list) {
        try {
          const items = await get<InventoryWithProduct[]>(
            `/api/v1/stores/${c.store.id}/preview?service_id=${c.service.id}&limit=${PREVIEW_LIMIT}`,
          );
          if (cancelled) return;
          if (items.length > 0) {
            setResolved({ store: c.store, service: c.service, items });
            setLoading(false);
            return;
          }
        } catch {
          // best-effort: try the next candidate
        }
      }
      if (!cancelled) {
        setResolved(null);
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [candidates]);

  if (loading) {
    return (
      <section className={styles.section} aria-busy="true">
        <div className={styles.skeletonHead} />
        <div className={styles.skeletonRail}>
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className={styles.skeletonCard} />
          ))}
        </div>
      </section>
    );
  }

  // Degenerate case: nothing to show AND the user has not set a location →
  // surface a location prompt instead of dead space.
  if (!resolved) {
    if (hydrated && !userSet) {
      return (
        <section className={styles.section}>
          <button
            type="button"
            className={styles.locCard}
            onClick={() => setPickerOpen(true)}
          >
            <span className={styles.locGlyph} aria-hidden>
              📍
            </span>
            <span>{t("previewSetLocationCard")}</span>
          </button>
          <DeliveryLocationPicker open={pickerOpen} onClose={() => setPickerOpen(false)} />
        </section>
      );
    }
    return null;
  }

  const { store, service, items } = resolved;
  // Per-service pause lives on the store's own services list (populated by the
  // store query); the catalog `service.is_paused` is only a schema default.
  const disabledByPause =
    store.is_paused ||
    (store.services.find((s) => s.id === service.id)?.is_paused ?? false);
  const showDistance = hydrated && userSet && store.distance_km != null;

  return (
    <section className={styles.section}>
      <div className={styles.head}>
        <div className={styles.headLeft}>
          <h2 className={styles.title}>{t("previewTitle")}</h2>
          <div className={styles.meta}>
            <span className={styles.storeName}>{store.name}</span>
            {!disabledByPause && (
              <span className={styles.openPill}>{t("previewOpenNow")}</span>
            )}
            <span className={styles.serviceTag}>{service.name}</span>
            {showDistance && (
              <span className={styles.distance}>
                {t("previewKmAway", { km: store.distance_km!.toFixed(1) })}
              </span>
            )}
          </div>
        </div>
        <Link href={`/stores/${store.id}`} className={styles.viewStore}>
          {t("previewViewStore")}
        </Link>
      </div>

      {hydrated && !userSet && (
        <button
          type="button"
          className={styles.locNudge}
          onClick={() => setPickerOpen(true)}
        >
          📍 {t("previewSetLocation")}
        </button>
      )}

      <ScrollRail ariaLabel={t("previewTitle")}>
        {items.map((item) => (
          <div key={item.id} className={styles.railItem}>
            <ProductCard
              item={item}
              storeId={store.id}
              storeName={store.name}
              serviceId={service.id}
              serviceName={service.name}
              disabledByPause={disabledByPause}
            />
          </div>
        ))}
      </ScrollRail>

      <DeliveryLocationPicker open={pickerOpen} onClose={() => setPickerOpen(false)} />
    </section>
  );
}
