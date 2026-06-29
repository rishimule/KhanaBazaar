"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { get } from "@/lib/api";
import { formatAddress } from "@/lib/format-address";
import { useAuth } from "@/lib/AuthContext";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { serviceGlyph } from "@/lib/serviceGlyph";
import { ScrollRail } from "@/components/ScrollRail";
import { HomeStorePreview, PreviewCandidate } from "@/components/HomeStorePreview";
import { NearbyLocationBanner } from "@/components/NearbyLocationBanner";
import { Service, Store } from "@/types";
import styles from "./page.module.css";

export default function Home() {
  const t = useTranslations("Home");
  const { dbUser, loading } = useAuth();
  const router = useRouter();
  const [stores, setStores] = useState<Store[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const { location } = useDeliveryLocation();

  useEffect(() => {
    if (loading || !dbUser) return;
    if (dbUser.role === "seller") {
      router.replace("/seller");
    } else if (dbUser.role === "admin") {
      router.replace("/admin");
    }
  }, [loading, dbUser, router]);

  useEffect(() => {
    const url = location
      ? `/api/v1/stores/?lat=${location.lat}&lng=${location.lng}&sort=distance`
      : "/api/v1/stores/";
    get<Store[]>(url)
      .then(setStores)
      .catch(() => setStores([]));
  }, [location]);

  useEffect(() => {
    get<Service[]>("/api/v1/catalog/services")
      .then((rows) =>
        setServices(
          rows
            .filter((s) => s.is_active !== false)
            .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id)
        )
      )
      .catch(() => setServices([]));
  }, []);

  const candidates = useMemo<PreviewCandidate[]>(() => {
    const out: PreviewCandidate[] = [];
    for (const service of services) {
      const store = stores.find((s) =>
        s.services?.some((sv) => sv.id === service.id),
      );
      if (store) out.push({ store, service });
    }
    return out;
  }, [services, stores]);

  if (loading || (dbUser && dbUser.role !== "customer")) {
    return (
      <div style={{ padding: "4rem", textAlign: "center", color: "var(--color-neutral-500)" }}>
        Loading…
      </div>
    );
  }

  // Honeycomb tiles, one per active service (capped at 40).
  const hexTiles = services.slice(0, 40).map((s, i) => (
    <Link
      key={s.id}
      href={`/products?service=${encodeURIComponent(s.slug)}`}
      className={`${styles.hexCell} ${styles[`hexC${i % 6}`]}`}
    >
      <span className={styles.hexInner}>
        <span className={styles.hexGlyph} aria-hidden>{serviceGlyph(s.slug)}</span>
        <span className={styles.hexLabel}>{s.name}</span>
      </span>
    </Link>
  ));
  // Group into interlocking columns: a single centred hex, then a stacked
  // top+bottom pair, alternating — the flat-top honeycomb pattern.
  const hexColumns: { center: boolean; tiles: typeof hexTiles }[] = [];
  for (let i = 0; i < hexTiles.length; ) {
    const center = hexColumns.length % 2 === 0;
    const take = center ? 1 : 2;
    hexColumns.push({ center, tiles: hexTiles.slice(i, i + take) });
    i += take;
  }

  return (
    <div className={styles.page}>
      <NearbyLocationBanner />
      <div className={styles.shell}>
        <section className={styles.hero}>
          <span className={styles.heroGlyph} aria-hidden>🥢</span>
          <div className={styles.eyebrow}>{t("badge")}</div>
          <h1 className={styles.heroTitle}>{t("heroTitle")}</h1>
          <p className={styles.heroSub}>{t("heroDescription")}</p>
          <div className={styles.heroCta}>
            <Link href="/products" className={styles.heroBtnPrimary}>
              {t("ctaExploreProducts")}
            </Link>
            <Link href="/stores" className={styles.heroBtnGhost}>
              {t("ctaStartShopping")}
            </Link>
            <Link href="/sell" className={styles.heroBtnGhost}>
              {t("ctaSellOnKB")}
            </Link>
          </div>
        </section>

        <section className={styles.promoRow}>
          <div className={`${styles.promoCard} ${styles.promoCardRefer}`}>
            <span className={styles.promoGlyph} aria-hidden>🎁</span>
            <div className={styles.promoEyebrow}>{t("trustPincode")}</div>
            <h3 className={styles.promoTitle}>Same-day delivery in 2 hours</h3>
            <Link href="/stores" className={styles.promoLink}>Browse nearby stores →</Link>
          </div>
        </section>

        {services.length > 0 && (
          <section className={styles.section}>
            <div className={styles.sectionHead}>
              <h2 className={styles.sectionTitle}>Shop by service</h2>
              <Link href="/products" className={styles.sectionMore}>More ›</Link>
            </div>
            <ScrollRail ariaLabel="Shop by service">
              <div className={styles.honeycombInner}>
                {hexColumns.map((col, ci) => (
                  <div
                    key={ci}
                    className={col.center ? styles.hcCol : `${styles.hcCol} ${styles.hcColPair}`}
                  >
                    {col.tiles}
                  </div>
                ))}
              </div>
            </ScrollRail>
          </section>
        )}

        <HomeStorePreview candidates={candidates} />

        <section className={styles.section}>
          <div className={styles.sectionHead}>
            <h2 className={styles.sectionTitle}>{t("popularTitle")}</h2>
            <Link href="/stores" className={styles.sectionMore}>{t("viewAllStores")} ›</Link>
          </div>

          {stores.length > 0 ? (
            <div className={styles.storesGrid}>
              {stores.slice(0, 8).map((store) => (
                <Link
                  key={store.id}
                  href={`/stores/${store.id}`}
                  className={styles.storeCard}
                >
                  <div className={styles.storeCardTop}>
                    <span className={styles.storeAvatar}>
                      {store.name.charAt(0).toUpperCase()}
                    </span>
                    <span className={styles.storeCardStatus}>{t("storeOpenNow")}</span>
                  </div>
                  <div className={styles.storeCardBody}>
                    <h3 className={styles.storeName}>{store.name}</h3>
                    <p className={styles.storeAddr}>{formatAddress(store.address)}</p>
                    <span className={styles.storeCardAction}>{t("storeBrowse")} →</span>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className={styles.emptyState}>
              <h3 className={styles.emptyTitle}>{t("emptyTitle")}</h3>
              <p className={styles.emptyBody}>{t("emptyBody")}</p>
              <Link href="/stores" className="btn btn-secondary">
                {t("emptyBrowseAll")}
              </Link>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
