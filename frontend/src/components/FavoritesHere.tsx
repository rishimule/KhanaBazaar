"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import ProductCard from "@/components/ProductCard";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import { useFavorites } from "@/lib/FavoritesContext";
import { favoriteToInventoryItem } from "@/lib/favorites";
import type { FavoriteAtStore } from "@/types";
import styles from "./FavoritesHere.module.css";

interface Props {
  storeId: number;
  storeName: string;
}

export default function FavoritesHere({ storeId, storeName }: Props) {
  const t = useTranslations("Favorites");
  const { dbUser, token } = useAuth();
  const { isFavorite, loaded: favsLoaded } = useFavorites();
  const [items, setItems] = useState<FavoriteAtStore[] | null>(null);

  useEffect(() => {
    if (dbUser?.role !== "customer" || !token) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- gate must clear stale data on logout / role change
      setItems(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await get<FavoriteAtStore[]>(
          `/api/v1/favorites/stores/${storeId}`,
          token,
        );
        if (!cancelled) setItems(res);
      } catch (e) {
        console.error("favorites: store rail failed", e);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [dbUser?.role, token, storeId, favsLoaded]);

  // Hide items the customer has just unfavourited (optimistic local filter).
  // Server-truth catches up on the next fetch (mount / favsLoaded flip).
  const visibleItems = useMemo(
    () => (items ?? []).filter((it) => isFavorite(it.product_id)),
    [items, isFavorite],
  );

  if (visibleItems.length === 0) return null;

  return (
    <section className={styles.rail}>
      <h2 className={styles.title}>{t("favouritesHere")}</h2>
      <div className={styles.scroller}>
        {visibleItems.map((it) => (
          <div key={it.product_id} className={styles.card}>
            <ProductCard
              item={favoriteToInventoryItem(it, storeId)}
              storeId={storeId}
              storeName={storeName}
              serviceId={it.service_id}
              serviceName={it.service_name}
            />
          </div>
        ))}
      </div>
    </section>
  );
}
