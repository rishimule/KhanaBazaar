"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useAuth } from "@/lib/AuthContext";
import styles from "./ProductMiniCard.module.css";

type Props = {
  href: string;
  name: string;
  imageUrl: string | null;
  brand?: string | null;
  minPrice: number;
  maxPrice: number;
  inStock: boolean;
  outOfStockLabel: string;
};

export function ProductMiniCard({
  href,
  name,
  imageUrl,
  brand,
  minPrice,
  maxPrice,
  inStock,
  outOfStockLabel,
}: Props) {
  const { dbUser } = useAuth();
  const role = dbUser?.role;
  // Shoppers only: guests and customers. Sellers/admins navigate via the card
  // body but never see a shopping "+".
  const canShop = !role || role === "customer";

  return (
    <Link href={href} className={styles.card}>
      <div className={styles.imageWrap}>
        {imageUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={imageUrl}
            alt={name}
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            className={styles.img}
          />
        ) : (
          <div aria-hidden className={styles.imgFallback}>
            🛒
          </div>
        )}
        {canShop && (
          // Decorative only: the whole card is one <Link>, so a nested button or
          // anchor would be invalid HTML. The "+" navigates by bubbling its click
          // to the parent <Link> (same destination as clicking the card).
          <span
            aria-hidden
            className={`${styles.addBtn} ${inStock ? "" : styles.addBtnMuted}`}
          >
            +
          </span>
        )}
      </div>
      <div className={styles.name}>{name}</div>
      {brand && <div className={styles.brand}>{brand}</div>}
      <div className={styles.price}>
        ₹{minPrice.toFixed(0)}
        {maxPrice !== minPrice && (
          <span className={styles.range}> – ₹{maxPrice.toFixed(0)}</span>
        )}
      </div>
      {!inStock && <div className={styles.badge}>{outOfStockLabel}</div>}
    </Link>
  );
}
