"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import ProductCard from "@/components/ProductCard";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import { useFavorites } from "@/lib/FavoritesContext";
import type { FavoriteAtStore, InventoryWithProduct } from "@/types";
import styles from "./FavoritesHere.module.css";

interface Props {
  storeId: number;
  storeName: string;
}

function toInventoryItem(
  it: FavoriteAtStore,
  storeId: number,
): InventoryWithProduct {
  return {
    id: it.inventory_id,
    store_id: storeId,
    product_id: it.product_id,
    price: it.price,
    stock: it.stock,
    is_available: it.stock > 0,
    created_at: it.favourited_at,
    updated_at: it.favourited_at,
    product: {
      id: it.product_id,
      name: it.name,
      description: "",
      category_id: it.category_id,
      subcategory_id: 0,
      subcategory_name: "",
      image_url: it.image_url ?? undefined,
      base_price: it.price,
      created_at: it.favourited_at,
      updated_at: it.favourited_at,
    },
  };
}

export default function FavoritesHere({ storeId, storeName }: Props) {
  const t = useTranslations("Favorites");
  const { dbUser, token } = useAuth();
  // Re-fetch when the customer toggles favourites elsewhere so the rail
  // reflects the latest server-truth without a full page reload.
  const { count: favCount, loaded: favsLoaded } = useFavorites();
  const [items, setItems] = useState<FavoriteAtStore[] | null>(null);

  useEffect(() => {
    if (dbUser?.role !== "customer" || !token) {
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
  }, [dbUser?.role, token, storeId, favCount, favsLoaded]);

  if (!items || items.length === 0) return null;

  return (
    <section className={styles.rail}>
      <h2 className={styles.title}>{t("favouritesHere")}</h2>
      <div className={styles.scroller}>
        {items.map((it) => (
          <div key={it.product_id} className={styles.card}>
            <ProductCard
              item={toInventoryItem(it, storeId)}
              storeId={storeId}
              storeName={storeName}
              serviceId={0}
              serviceName=""
            />
          </div>
        ))}
      </div>
    </section>
  );
}
