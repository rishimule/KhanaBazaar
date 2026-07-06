"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useCart } from "@/lib/CartContext";
import { useAuth } from "@/lib/AuthContext";
import { useFavorites } from "@/lib/FavoritesContext";
import { pushRecentlyViewed } from "@/lib/recentlyViewed";
import type { StoreProductDetail } from "@/types";
import ProductGallery from "./ProductGallery";
import ReviewsPanel from "./ReviewsPanel";
import CrownBadge from "@/components/CrownBadge";
import styles from "./ProductDetail.module.css";

interface Props {
  data: StoreProductDetail;
  variant: "modal" | "page";
}

export default function ProductDetail({ data, variant }: Props) {
  const t = useTranslations("Product");
  const { carts, addItem, removeItem, updateQty } = useCart();
  const { dbUser } = useAuth();
  const { isFavorite, toggle: toggleFav } = useFavorites();
  const [addError, setAddError] = useState(false);

  const { store, service, inventory } = data;
  const { product, price, stock, is_available: isAvailable } = inventory;

  useEffect(() => {
    pushRecentlyViewed({
      product_id: product.id,
      store_id: store.id,
      name: product.name,
      image_url: product.image_url ?? null,
    });
  }, [product.id, product.name, product.image_url, store.id]);

  const role = dbUser?.role;
  const canShop = !role || role === "customer";
  const canBuy = canShop && isAvailable && stock > 0;

  const cart = carts.find(
    (c) => c.store_id === store.id && c.service_id === service.id,
  );
  const qty = cart?.items.find((i) => i.product_id === product.id)?.quantity ?? 0;

  const stockLabel =
    !isAvailable
      ? t("unavailable")
      : stock === 0
      ? t("outOfStock")
      : stock <= 5
      ? t("onlyNLeft", { count: stock })
      : t("inStock");
  const stockClass =
    !isAvailable || stock === 0
      ? styles.outOfStock
      : stock <= 5
      ? styles.lowStock
      : styles.inStock;

  const handleAdd = async () => {
    setAddError(false);
    try {
      await addItem(store.id, store.name, service.id, service.name, {
        product_id: product.id,
        inventory_id: inventory.id,
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

  return (
    <article className={`${styles.detail} ${styles[variant]}`}>
      <ProductGallery
        images={product.images ?? []}
        imageUrl={product.image_url}
        productName={product.name}
        variant={variant}
      />

      <div className={styles.body}>
        <div className={styles.titleRow}>
          <h1 className={styles.name}>{product.name}</h1>
          {dbUser?.role === "customer" && (
            <button
              type="button"
              className={`${styles.heart} ${isFavorite(product.id) ? styles.heartActive : ""}`}
              onClick={() => void toggleFav(product.id)}
              aria-label={isFavorite(product.id) ? t("removeFromFavorites") : t("addToFavorites")}
              aria-pressed={isFavorite(product.id)}
            >
              <svg width="22" height="22" viewBox="0 0 24 24"
                fill={isFavorite(product.id) ? "currentColor" : "none"}
                stroke="currentColor" strokeWidth="2"
                strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
              </svg>
            </button>
          )}
        </div>
        <p className={styles.context}>
          {store.name}{store.is_premium && <CrownBadge />} · {service.name}
        </p>
        <div className={styles.price}>₹{Number(price).toFixed(2)}</div>
        <span className={`${styles.stockBadge} ${stockClass}`}>{stockLabel}</span>

        {canShop && (
          <div className={styles.actions}>
            {qty === 0 ? (
              <button
                className={styles.addBtn}
                onClick={() => void handleAdd()}
                disabled={!canBuy}
                aria-label={canBuy ? t("addToCart") : t("outOfStockButton")}
              >
                {canBuy ? t("addToCart") : t("outOfStockButton")}
              </button>
            ) : (
              <div className={styles.qtyControls} role="group" aria-label="Quantity">
                <button
                  className={styles.qtyBtn}
                  onClick={() =>
                    qty <= 1
                      ? removeItem(store.id, service.id, product.id)
                      : updateQty(store.id, service.id, product.id, qty - 1)
                  }
                  aria-label={t("decreaseQty")}
                >
                  −
                </button>
                <span className={styles.qtyValue}>{qty}</span>
                <button
                  className={styles.qtyBtn}
                  onClick={() =>
                    updateQty(store.id, service.id, product.id, qty + 1)
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
        {addError && (
          <p className={styles.addError} role="alert">{t("addToCartFailed")}</p>
        )}

        {product.description && (
          <section className={styles.description}>
            <h2 className={styles.sectionTitle}>{t("description")}</h2>
            <p>{product.description}</p>
          </section>
        )}

        <ReviewsPanel storeName={store.name} />
      </div>
    </article>
  );
}
