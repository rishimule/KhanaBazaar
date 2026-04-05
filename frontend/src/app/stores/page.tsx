import type { Metadata } from "next";
import Link from "next/link";
import { mockStores, getStoreItemCount } from "@/lib/mock-data";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Browse Stores",
  description: "Discover local stores near you on Khana Bazaar.",
};

export default function StoresPage() {
  return (
    <div className={styles.page}>
      <div className={styles.pageInner}>
        {/* Header */}
        <div className={styles.header}>
          <h1 className={styles.title}>
            Browse <span className={styles.titleAccent}>Stores</span>
          </h1>
          <p className={styles.subtitle}>
            Select a store to see what&apos;s available near you
          </p>
        </div>

        {/* Store Grid */}
        <div className={styles.grid}>
          {mockStores.map((store) => (
            <Link
              key={store.id}
              href={`/stores/${store.id}`}
              className={styles.card}
              id={`store-card-${store.id}`}
            >
              <div className={styles.cardIcon}>🏪</div>
              <h2 className={styles.cardName}>{store.name}</h2>
              <p className={styles.cardAddress}>{store.address}</p>
              <div className={styles.cardMeta}>
                <span className={styles.cardItems}>
                  📦 {getStoreItemCount(store.id)} items
                </span>
                <span className={styles.cardStatus}>● Open</span>
              </div>
              <span className={styles.viewBtn}>
                View Store →
              </span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
