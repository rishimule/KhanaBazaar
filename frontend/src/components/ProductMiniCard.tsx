"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
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
  return (
    <Link href={href} className={styles.card}>
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
