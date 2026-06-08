"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useRouter } from "next/navigation";
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
  const router = useRouter();
  const { dbUser } = useAuth();
  const role = dbUser?.role;
  // Shoppers only: guests and customers see the "+". Sellers/admins browse via
  // the card body but get no shopping affordance.
  const canShop = !role || role === "customer";

  return (
    <div className={styles.card}>
      {/* Stretched link covers the whole card so any click on it navigates to
          the compare page. Kept empty (label only) so the "+" can be a real,
          focusable <button> sibling instead of an invalid <button> nested in
          an <a>. */}
      <Link href={href} aria-label={name} className={styles.stretched} />
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
      </div>
      <div className={styles.name}>{name}</div>
      {brand && <div className={styles.brand}>{brand}</div>}
      <div className={styles.priceRow}>
        <span className={styles.price}>
          ₹{minPrice.toFixed(0)}
          {maxPrice !== minPrice && (
            <span className={styles.range}> – ₹{maxPrice.toFixed(0)}</span>
          )}
        </span>
        {canShop && (
          <button
            type="button"
            className={styles.addBtn}
            disabled={!inStock}
            onClick={() => router.push(href)}
            aria-label={`View prices for ${name}`}
          >
            +
          </button>
        )}
      </div>
      {!inStock && <div className={styles.badge}>{outOfStockLabel}</div>}
    </div>
  );
}
