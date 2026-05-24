"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { get } from "@/lib/api";
import { formatAddress } from "@/lib/format-address";
import { useAuth } from "@/lib/AuthContext";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { serviceGlyph } from "@/lib/serviceGlyph";
import { Service, Store } from "@/types";
import styles from "./page.module.css";

export default function Home() {
  const t = useTranslations("Home");
  const { dbUser, loading } = useAuth();
  const router = useRouter();
  const [stores, setStores] = useState<Store[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const { location } = useDeliveryLocation();

  const railRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const updateArrows = useCallback(() => {
    const el = railRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 1);
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
  }, []);

  const scrollRail = useCallback((dir: -1 | 1) => {
    const el = railRef.current;
    if (!el) return;
    el.scrollBy({ left: dir * el.clientWidth * 0.8, behavior: "smooth" });
  }, []);

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

  useEffect(() => {
    updateArrows();
    window.addEventListener("resize", updateArrows);
    return () => window.removeEventListener("resize", updateArrows);
  }, [services, updateArrows]);

  if (loading || (dbUser && dbUser.role !== "customer")) {
    return (
      <div style={{ padding: "4rem", textAlign: "center", color: "var(--color-neutral-500)" }}>
        Loading…
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.shell}>
        <section className={styles.hero}>
          <span className={styles.heroGlyph} aria-hidden>🥢</span>
          <div className={styles.eyebrow}>{t("badge")}</div>
          <h1 className={styles.heroTitle}>{t("heroTitle")}</h1>
          <p className={styles.heroSub}>{t("heroDescription")}</p>
          <div className={styles.heroCta}>
            <Link href="/stores" className={styles.heroBtnPrimary}>
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
            <span className={styles.promoLink}>Browse nearby stores →</span>
          </div>
          <div className={`${styles.promoCard} ${styles.promoCardMember}`}>
            <span className={styles.promoGlyph} aria-hidden>👑</span>
            <div className={styles.promoEyebrow}>{t("trustUpi")}</div>
            <h3 className={styles.promoTitle}>Pay with UPI · zero card hassle</h3>
            <span className={`${styles.promoLink} ${styles.promoLinkDark}`}>Learn how →</span>
          </div>
        </section>

        {services.length > 0 && (
          <section className={styles.section}>
            <div className={styles.sectionHead}>
              <h2 className={styles.sectionTitle}>Shop by service</h2>
              <Link href="/stores" className={styles.sectionMore}>More ›</Link>
            </div>
            <div className={styles.svcRailWrap}>
              {canScrollLeft && (
                <button
                  type="button"
                  className={`${styles.svcArrow} ${styles.svcArrowLeft}`}
                  onClick={() => scrollRail(-1)}
                  aria-label="Scroll left"
                >
                  ‹
                </button>
              )}
              <div ref={railRef} onScroll={updateArrows} className={styles.svcGrid}>
                {services.map((s) => (
                  <Link
                    key={s.id}
                    href={`/stores?service=${encodeURIComponent(s.slug)}`}
                    className={styles.catTile}
                  >
                    <span className={styles.catTileGlyph} aria-hidden>{serviceGlyph(s.slug)}</span>
                    <span className={styles.catTileLabel}>{s.name}</span>
                  </Link>
                ))}
              </div>
              {canScrollRight && (
                <button
                  type="button"
                  className={`${styles.svcArrow} ${styles.svcArrowRight}`}
                  onClick={() => scrollRail(1)}
                  aria-label="Scroll right"
                >
                  ›
                </button>
              )}
            </div>
          </section>
        )}

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

        <section className={styles.sellerBand}>
          <div>
            <span className={styles.eyebrow}>{t("sellerBandEyebrow")}</span>
            <h2 className={styles.sellerBandTitle}>{t("sellerBandTitle")}</h2>
            <p className={styles.sellerBandSub}>{t("sellerBandBody")}</p>
          </div>
          <Link href="/sell" className="btn btn-primary">
            {t("becomeSeller")}
          </Link>
        </section>
      </div>
    </div>
  );
}
