"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import { Store } from "@/types";
import styles from "./page.module.css";

export default function StoresPage() {
  const router = useRouter();
  const { dbUser, loading } = useAuth();
  const [stores, setStores] = useState<Store[]>([]);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (!loading && !dbUser) {
      router.push("/login");
      return;
    }
    if (!loading && dbUser) {
      get<Store[]>("/api/v1/stores/")
        .then(setStores)
        .catch(() => setStores([]))
        .finally(() => setFetching(false));
    }
  }, [loading, dbUser, router]);

  if (loading || fetching) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <div className={styles.header}>
            <h1 className={styles.title}>Loading…</h1>
          </div>
        </div>
      </div>
    );
  }

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
          {stores.map((store) => (
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
