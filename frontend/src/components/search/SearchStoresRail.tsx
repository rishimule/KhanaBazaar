"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import { useEffect, useState } from "react";
import { useLocale } from "next-intl";
import { searchStores, type StoreHit } from "@/lib/searchClient";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import CrownBadge from "@/components/CrownBadge";
import styles from "./SearchStoresRail.module.css";

export function SearchStoresRail({ q }: { q: string }) {
  const locale = useLocale();
  const { location } = useDeliveryLocation();
  const [stores, setStores] = useState<StoreHit[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!q.trim()) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clear when q empties
      setStores([]);
      return;
    }
    let cancel = false;
    setLoading(true);
    searchStores({
      q,
      lat: location?.lat,
      lng: location?.lng,
      page: 1,
      pageSize: 6,
    })
      .then((res) => {
        if (!cancel) setStores(res.stores);
      })
      .catch(() => {
        if (!cancel) setStores([]);
      })
      .finally(() => {
        if (!cancel) setLoading(false);
      });
    return () => {
      cancel = true;
    };
  }, [q, location]);

  if (loading || stores.length === 0) return null;

  return (
    <section className={styles.section} aria-label="Stores">
      <h2 className={styles.heading}>Stores matching &quot;{q}&quot;</h2>
      <div className={styles.row}>
        {stores.map((s) => (
          <Link key={s.id} href={`/${locale}/stores/${s.id}`} className={styles.card}>
            <span className={styles.icon} aria-hidden>
              🏪
            </span>
            <span className={styles.body}>
              <span className={styles.nameRow}>
                <span className={styles.name}>{s.name}</span>
                {s.is_premium && <CrownBadge />}
              </span>
              {s.distance_km != null && (
                <span className={styles.dist}>{s.distance_km} km away</span>
              )}
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
