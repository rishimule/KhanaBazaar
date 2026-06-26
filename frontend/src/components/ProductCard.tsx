"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useCart } from "@/lib/CartContext";
import { useAuth } from "@/lib/AuthContext";
import { useFavorites } from "@/lib/FavoritesContext";
import { InventoryWithProduct } from "@/types";
import styles from "./ProductCard.module.css";

interface Props {
  item: InventoryWithProduct;
  storeId: number;
  storeName: string;
  serviceId: number;
  serviceName: string;
  /** When the store or this service is paused, ordering is disabled. */
  disabledByPause?: boolean;
  /** Set for the first above-the-fold cards so their image loads eagerly with
   *  high fetch priority (LCP). Default false → lazy. */
  priority?: boolean;
}

const CATEGORY_EMOJI: Record<number, string> = {
  1: "🥬",
  2: "🥛",
  3: "🌾",
  4: "🍪",
};

const CATEGORY_ACCENT: Record<number, string> = {
  1: "#d7fae1",
  2: "#fef9c3",
  3: "#fde68a",
  4: "#feefdb",
};

function HeartIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
    </svg>
  );
}

export default function ProductCard({
  item, storeId, storeName, serviceId, serviceName, disabledByPause = false, priority = false,
}: Props) {
  const t = useTranslations("Product");
  const locale = useLocale();
  const { carts, addItem, removeItem, updateQty } = useCart();
  const { dbUser } = useAuth();
  const { isFavorite, toggle } = useFavorites();
  const { product, price, stock } = item;
  const [imgFailed, setImgFailed] = useState(false);
  const [addError, setAddError] = useState(false);
  const isCustomer = dbUser?.role === "customer";
  const wishlist = isCustomer && isFavorite(product.id);

  const productHref = `/${locale}/stores/${storeId}/p/${product.id}`;

  const role = dbUser?.role;
  const canShop = !role || role === "customer";

  const cart = carts.find(
    (c) => c.store_id === storeId && c.service_id === serviceId,
  );
  const cartItem = cart?.items.find((i) => i.product_id === product.id);
  const qty = cartItem?.quantity ?? 0;

  const stockLabel =
    stock === 0
      ? t("outOfStock")
      : stock <= 5
      ? t("onlyNLeft", { count: stock })
      : t("inStock");
  const stockClass =
    stock === 0 ? styles.outOfStock : stock <= 5 ? styles.lowStock : styles.inStock;

  const handleAdd = async () => {
    if (disabledByPause) return;
    setAddError(false);
    try {
      await addItem(storeId, storeName, serviceId, serviceName, {
        product_id: product.id,
        inventory_id: item.id,
        product_name: product.name,
        quantity: 1,
        price,
        image_url: product.image_url,
      });
    } catch {
      setAddError(true);
      setTimeout(() => setAddError(false), 3000);
    }
  };

  const accent = CATEGORY_ACCENT[product.category_id] ?? "var(--shade-cool-light-1)";
  const glyph = CATEGORY_EMOJI[product.category_id] ?? "📦";
  const showImage = Boolean(product.image_url) && !imgFailed;

  return (
    <div className={styles.card}>
      <Link href={productHref} prefetch className={styles.imageLink}>
        <div className={styles.imageWrap} style={{ background: accent }}>
          {showImage ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={product.image_url}
              alt={product.name}
              loading={priority ? "eager" : "lazy"}
              fetchPriority={priority ? "high" : "auto"}
              decoding="async"
              referrerPolicy="no-referrer"
              onError={() => setImgFailed(true)}
            />
          ) : (
            <span className={styles.imagePlaceholder} aria-hidden>{glyph}</span>
          )}
          {stock === 0 && (
            <div className={styles.badges}>
              <span className="badge badge--neutral">SOLD OUT</span>
            </div>
          )}
        </div>
      </Link>

      {isCustomer && (
        <button
          type="button"
          className={`${styles.heart} ${wishlist ? styles.heartActive : ""}`}
          onClick={() => void toggle(product.id)}
          aria-label={wishlist ? t("removeFromFavorites") : t("addToFavorites")}
          aria-pressed={wishlist}
        >
          <HeartIcon filled={wishlist} />
        </button>
      )}

      <div className={styles.meta}>
        <Link href={productHref} prefetch className={styles.nameLink}>
          <div className={styles.name}>{product.name}</div>
        </Link>
        <div className={styles.priceRow}>
          <span className={styles.price}>
            ₹{Number(price).toFixed(2)}
          </span>
        </div>
        <span className={`${styles.stockBadge} ${stockClass}`}>{stockLabel}</span>

        {canShop && (
          <div className={styles.actions}>
            {addError && (
              <span className={styles.addError} role="alert">
                {t("addToCartFailed")}
              </span>
            )}
            {qty === 0 ? (
              <button
                className={styles.addBtn}
                onClick={() => void handleAdd()}
                disabled={stock === 0 || disabledByPause}
                aria-label={stock === 0 ? t("outOfStockButton") : t("addToCart")}
              >
                +
              </button>
            ) : (
              <div className={styles.qtyControls} role="group" aria-label="Quantity">
                <button
                  className={styles.qtyBtn}
                  onClick={() =>
                    qty <= 1
                      ? removeItem(storeId, serviceId, product.id)
                      : updateQty(storeId, serviceId, product.id, qty - 1)
                  }
                  aria-label={t("decreaseQty")}
                >
                  −
                </button>
                <span className={styles.qtyValue}>{qty}</span>
                <button
                  className={styles.qtyBtn}
                  onClick={() =>
                    updateQty(storeId, serviceId, product.id, qty + 1)
                  }
                  disabled={qty >= stock}
                  aria-label={t("increaseQty")}
                >
                  +
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
