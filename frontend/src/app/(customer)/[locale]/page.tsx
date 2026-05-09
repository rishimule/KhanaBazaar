"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { get } from "@/lib/api";
import { formatAddress } from "@/lib/format-address";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { Store } from "@/types";
import styles from "./page.module.css";

export default function Home() {
  const t = useTranslations("Home");
  const [stores, setStores] = useState<Store[]>([]);
  const { location } = useDeliveryLocation();

  useEffect(() => {
    const url = location
      ? `/api/v1/stores/?lat=${location.lat}&lng=${location.lng}&sort=distance`
      : "/api/v1/stores/";
    get<Store[]>(url)
      .then(setStores)
      .catch(() => setStores([]));
  }, [location]);

  const shoppingHref = "/stores";
  const shoppingLabel = t("ctaStartShopping");

  return (
    <>
      <section className={styles.hero}>
        <div className={styles.heroInner}>
          <div className={styles.heroCopy}>
            <div className={styles.badge}>
              <span className={styles.badgeDot} />
              {t("badge")}
            </div>

            <h1 className={styles.heroTitle}>{t("heroTitle")}</h1>

            <p className={styles.heroDescription}>{t("heroDescription")}</p>

            <div className={styles.heroCta}>
              <Link
                href={shoppingHref}
                className="btn btn-primary"
                id="cta-start-shopping"
              >
                {shoppingLabel}
              </Link>
              <Link
                href="/sell"
                className="btn btn-outline"
                id="cta-become-seller"
              >
                {t("ctaSellOnKB")}
              </Link>
            </div>

            <div
              className={styles.trustChips}
              aria-label={t("highlightsAria")}
            >
              <span>{t("trustPincode")}</span>
              <span>{t("trustInventory")}</span>
              <span>{t("trustUpi")}</span>
            </div>
          </div>

          <div className={styles.heroVisual} aria-hidden="true">
            <div className={styles.marketCard}>
              <div className={styles.marketHeader}>
                <span>{t("marketBasket")}</span>
                <strong>{t("marketToday")}</strong>
              </div>

              <div className={styles.produceGrid}>
                <span className={styles.produceItem} />
                <span className={styles.produceItem} />
                <span className={styles.produceItem} />
                <span className={styles.produceItem} />
              </div>

              <div className={styles.orderPanel}>
                <div>
                  <span className={styles.orderLabel}>{t("marketNearbyStore")}</span>
                  <strong>{t("marketFreshMart")}</strong>
                </div>
                <span className={styles.statusPill}>{t("marketOpenNow")}</span>
              </div>

              <div className={styles.deliveryCard}>
                <span className={styles.deliveryIcon} />
                <div>
                  <strong>{t("marketAreaMatched")}</strong>
                  <span>{t("marketAreaSubtitle")}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className={styles.benefitsSection}>
        <div className={styles.sectionInner}>
          <div className={styles.benefitsGrid}>
            <article className={styles.benefitCard}>
              <span
                className={`${styles.benefitIcon} ${styles.benefitIconPrimary}`}
              />
              <h2>{t("benefitShopNearbyTitle")}</h2>
              <p>{t("benefitShopNearbyBody")}</p>
            </article>

            <article className={styles.benefitCard}>
              <span
                className={`${styles.benefitIcon} ${styles.benefitIconAccent}`}
              />
              <h2>{t("benefitFreshTitle")}</h2>
              <p>{t("benefitFreshBody")}</p>
            </article>

            <article className={styles.benefitCard}>
              <span
                className={`${styles.benefitIcon} ${styles.benefitIconInfo}`}
              />
              <h2>{t("benefitMobileTitle")}</h2>
              <p>{t("benefitMobileBody")}</p>
            </article>
          </div>
        </div>
      </section>

      <section className={styles.storesSection}>
        <div className={styles.sectionInner}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionEyebrow}>{t("popularEyebrow")}</span>
            <h2>{t("popularTitle")}</h2>
            <p>{t("popularSubtitle")}</p>
          </div>

          {stores.length > 0 ? (
            <div className={styles.storesGrid}>
              {stores.map((store) => (
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
                  <h3>{store.name}</h3>
                  <p>{formatAddress(store.address)}</p>
                  <span className={styles.storeCardAction}>{t("storeBrowse")}</span>
                </Link>
              ))}
            </div>
          ) : (
            <div className={styles.emptyState}>
              <span className={styles.emptyStateIcon} />
              <h3>{t("emptyTitle")}</h3>
              <p>{t("emptyBody")}</p>
              <Link href={shoppingHref} className="btn btn-outline">
                {t("emptyBrowseAll")}
              </Link>
            </div>
          )}

          <div className={styles.storesSectionCta}>
            <Link href={shoppingHref} className="btn btn-outline">
              {t("viewAllStores")}
            </Link>
          </div>
        </div>
      </section>

      <section className={styles.sellerBand}>
        <div className={styles.sellerBandInner}>
          <div>
            <span className={styles.sectionEyebrow}>{t("sellerBandEyebrow")}</span>
            <h2>{t("sellerBandTitle")}</h2>
            <p>{t("sellerBandBody")}</p>
          </div>

          <Link href="/sell" className="btn btn-accent">
            {t("becomeSeller")}
          </Link>
        </div>
      </section>
    </>
  );
}
