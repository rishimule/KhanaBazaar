"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import { Store } from "@/types";
import styles from "./page.module.css";

export default function Home() {
  const { dbUser } = useAuth();
  const [stores, setStores] = useState<Store[]>([]);

  useEffect(() => {
    get<Store[]>("/api/v1/stores/")
      .then(setStores)
      .catch(() => setStores([]));
  }, []);

  const shoppingHref = dbUser ? "/stores" : "/login";
  const shoppingLabel = dbUser ? "Start shopping" : "Sign in to shop";

  return (
    <>
      <section className={styles.hero}>
        <div className={styles.heroInner}>
          <div className={styles.heroCopy}>
            <div className={styles.badge}>
              <span className={styles.badgeDot} />
              Premium local grocery
            </div>

            <h1 className={styles.heroTitle}>
              Daily essentials from trusted neighborhood stores
            </h1>

            <p className={styles.heroDescription}>
              Browse nearby sellers, compare local inventory, and shop fresh
              groceries and daily needs through a fast Indian-market checkout
              flow.
            </p>

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
                Sell on Khana Bazaar
              </Link>
            </div>

            <div
              className={styles.trustChips}
              aria-label="Marketplace highlights"
            >
              <span>Pincode-first discovery</span>
              <span>Local seller inventory</span>
              <span>UPI-ready commerce</span>
            </div>
          </div>

          <div className={styles.heroVisual} aria-hidden="true">
            <div className={styles.marketCard}>
              <div className={styles.marketHeader}>
                <span>Khana Basket</span>
                <strong>Today</strong>
              </div>

              <div className={styles.produceGrid}>
                <span className={styles.produceItem} />
                <span className={styles.produceItem} />
                <span className={styles.produceItem} />
                <span className={styles.produceItem} />
              </div>

              <div className={styles.orderPanel}>
                <div>
                  <span className={styles.orderLabel}>Nearby store</span>
                  <strong>Fresh Mart Local</strong>
                </div>
                <span className={styles.statusPill}>Open now</span>
              </div>

              <div className={styles.deliveryCard}>
                <span className={styles.deliveryIcon} />
                <div>
                  <strong>Area matched</strong>
                  <span>Inventory shown for your pincode</span>
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
              <h2>Shop nearby</h2>
              <p>
                Find stores serving your area and order from sellers your
                neighborhood already knows.
              </p>
            </article>

            <article className={styles.benefitCard}>
              <span
                className={`${styles.benefitIcon} ${styles.benefitIconAccent}`}
              />
              <h2>Fresh essentials</h2>
              <p>
                Browse groceries and daily needs from local sellers with
                practical inventory updates.
              </p>
            </article>

            <article className={styles.benefitCard}>
              <span
                className={`${styles.benefitIcon} ${styles.benefitIconInfo}`}
              />
              <h2>Built for mobile</h2>
              <p>
                Add Khana Bazaar to your home screen for a focused app-like
                ordering experience.
              </p>
            </article>
          </div>
        </div>
      </section>

      <section className={styles.storesSection}>
        <div className={styles.sectionInner}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionEyebrow}>Nearby marketplace</span>
            <h2>Popular stores</h2>
            <p>
              Start with local sellers and build your basket around what is
              available near you.
            </p>
          </div>

          {stores.length > 0 ? (
            <div className={styles.storesGrid}>
              {stores.map((store) => (
                <Link
                  key={store.id}
                  href={dbUser ? `/stores/${store.id}` : "/login"}
                  className={styles.storeCard}
                >
                  <div className={styles.storeCardTop}>
                    <span className={styles.storeAvatar}>
                      {store.name.charAt(0).toUpperCase()}
                    </span>
                    <span className={styles.storeCardStatus}>Open now</span>
                  </div>
                  <h3>{store.name}</h3>
                  <p>{store.address}</p>
                  <span className={styles.storeCardAction}>Browse store</span>
                </Link>
              ))}
            </div>
          ) : (
            <div className={styles.emptyState}>
              <span className={styles.emptyStateIcon} />
              <h3>Stores are being prepared for your area.</h3>
              <p>
                Check available sellers and start browsing as stores come
                online.
              </p>
              <Link href={shoppingHref} className="btn btn-outline">
                {dbUser ? "Browse all stores" : "Sign in to browse"}
              </Link>
            </div>
          )}

          <div className={styles.storesSectionCta}>
            <Link href={shoppingHref} className="btn btn-outline">
              View all stores
            </Link>
          </div>
        </div>
      </section>

      <section className={styles.sellerBand}>
        <div className={styles.sellerBandInner}>
          <div>
            <span className={styles.sectionEyebrow}>For local sellers</span>
            <h2>Run a local store?</h2>
            <p>
              Bring your catalog online, manage local inventory, and reach
              nearby customers through Khana Bazaar.
            </p>
          </div>

          <Link href="/sell" className="btn btn-accent">
            Become a seller
          </Link>
        </div>
      </section>
    </>
  );
}
