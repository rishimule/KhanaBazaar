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

  return (
    <>
      {/* Hero section */}
      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <div className={styles.badge}>
            <span className={styles.badgeDot} />
            Now in Development
          </div>

          <h1 className={styles.heroTitle}>
            Shop Local,{" "}
            <span className={styles.heroTitleAccent}>Delivered Fast</span>
          </h1>

          <p className={styles.heroDescription}>
            Your neighbourhood stores, now at your fingertips. Browse fresh
            groceries &amp; essentials from nearby sellers and enjoy seamless
            checkout.
          </p>

          <div className={styles.heroCta}>
            {dbUser ? (
              <Link href="/stores" className="btn btn-primary" id="cta-start-shopping">
                Start Shopping
              </Link>
            ) : (
              <Link href="/login" className="btn btn-primary" id="cta-start-shopping">
                Sign In to Shop
              </Link>
            )}
            <Link href="/sell" className="btn btn-outline" id="cta-become-seller">
              Sell on Khana Bazaar
            </Link>
          </div>

          {/* Features */}
          <div className={styles.features}>
            <div className={styles.featureCard}>
              <div className={`${styles.featureIcon} ${styles.featureIconPrimary}`}>🏪</div>
              <h3 className={styles.featureTitle}>Hyperlocal Stores</h3>
              <p className={styles.featureDescription}>
                Discover stores in your pin code area. Each store has its own
                curated selection and live inventory.
              </p>
            </div>

            <div className={styles.featureCard}>
              <div className={`${styles.featureIcon} ${styles.featureIconAccent}`}>⚡</div>
              <h3 className={styles.featureTitle}>Seamless Checkout</h3>
              <p className={styles.featureDescription}>
                Place your orders quickly. (Note: UPI and direct payment integrations are coming in a future update).
              </p>
            </div>

            <div className={styles.featureCard}>
              <div className={`${styles.featureIcon} ${styles.featureIconInfo}`}>📱</div>
              <h3 className={styles.featureTitle}>Install as App</h3>
              <p className={styles.featureDescription}>
                Works as a Progressive Web App. Add to your home screen for a
                native app-like experience.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Browse Stores section */}
      <section className={styles.storesSection}>
        <div className={styles.storesSectionInner}>
          <div className={styles.storesSectionHeader}>
            <h2 className={styles.storesSectionTitle}>
              Popular <span className={styles.heroTitleAccent}>Stores</span>
            </h2>
            <p className={styles.storesSectionSubtitle}>
              Browse nearby stores and start adding items to your cart
            </p>
          </div>

          <div className={styles.storesGrid}>
            {stores.map((store) => (
              <Link
                key={store.id}
                href={dbUser ? `/stores/${store.id}` : "/login"}
                className={styles.storeCard}
              >
                <div className={styles.storeCardIcon}>🏪</div>
                <h3 className={styles.storeCardName}>{store.name}</h3>
                <p className={styles.storeCardAddress}>{store.address}</p>
                <div className={styles.storeCardMeta}>
                  <span className={styles.storeCardStatus}>● Open</span>
                </div>
              </Link>
            ))}
          </div>

          <div className={styles.storesSectionCta}>
            <Link href={dbUser ? "/stores" : "/login"} className="btn btn-outline">
              View All Stores →
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
