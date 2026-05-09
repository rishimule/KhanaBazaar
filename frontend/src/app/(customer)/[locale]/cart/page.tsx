"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { useCart } from "@/lib/CartContext";
import { apiErrorKey } from "@/lib/errors";
import styles from "./page.module.css";

export default function CartPage() {
  const t = useTranslations("Cart");
  const tErr = useTranslations("Errors");
  const { carts, removeItem, updateQty, clearStoreCart, getTotal } = useCart();
  const { dbUser } = useAuth();
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleClear = async (storeId: number) => {
    setErrorMsg(null);
    try {
      await clearStoreCart(storeId);
    } catch (err) {
      const key = apiErrorKey(err);
      if (key) {
        setErrorMsg(tErr(key.replace(/^Errors\./, "")));
      } else {
        const detail =
          (err as { detail?: string })?.detail ??
          (err instanceof Error ? err.message : null);
        setErrorMsg(detail ?? t("errClear"));
      }
    }
  };

  const handleRemove = async (storeId: number, productId: number) => {
    setErrorMsg(null);
    try {
      await removeItem(storeId, productId);
    } catch (err) {
      const key = apiErrorKey(err);
      if (key) {
        setErrorMsg(tErr(key.replace(/^Errors\./, "")));
      } else {
        const detail =
          (err as { detail?: string })?.detail ??
          (err instanceof Error ? err.message : null);
        setErrorMsg(detail ?? t("errRemove"));
      }
    }
  };

  const handleUpdateQty = async (
    storeId: number,
    productId: number,
    qty: number
  ) => {
    setErrorMsg(null);
    try {
      await updateQty(storeId, productId, qty);
    } catch (err) {
      const key = apiErrorKey(err);
      if (key) {
        setErrorMsg(tErr(key.replace(/^Errors\./, "")));
      } else {
        const detail =
          (err as { detail?: string })?.detail ??
          (err instanceof Error ? err.message : null);
        setErrorMsg(detail ?? t("errUpdateQty"));
      }
    }
  };

  if (carts.length === 0) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <div className={styles.empty}>
            <div className={styles.emptyIcon}>🛒</div>
            <h1 className={styles.emptyTitle}>{t("emptyTitle")}</h1>
            <p className={styles.emptyText}>{t("emptyBody")}</p>
            <Link href="/stores" className="btn btn-primary" id="empty-cart-shop">
              {t("startShopping")}
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const isCustomer = dbUser?.role === "customer";

  const renderCheckoutCta = (storeId: number, subtotal: number) => {
    if (!dbUser) {
      return (
        <Link href={`/login?next=/checkout/${storeId}`} className={styles.checkoutBtn}>
          {t("loginToCheckout")}
        </Link>
      );
    }
    if (!isCustomer) {
      return (
        <span className={styles.checkoutBtn} aria-disabled>
          {t("customerLoginRequired")}
        </span>
      );
    }
    return (
      <Link href={`/checkout/${storeId}`} className={styles.checkoutBtn}>
        {t("checkoutCta", { subtotal })}
      </Link>
    );
  };

  const totalItems = carts.reduce(
    (sum, c) => sum + c.items.reduce((s, i) => s + i.quantity, 0),
    0
  );

  return (
    <div className={styles.page}>
      <div className={styles.pageInner}>
        <div className={styles.header}>
          <h1 className={styles.title}>
            {t("yourLabel")} <span className={styles.titleAccent}>{t("cartLabel")}</span>
          </h1>
          <p className={styles.subtitle}>
            {t("summary", { stores: carts.length, items: totalItems })}
          </p>
        </div>

        {errorMsg ? (
          <div role="alert" className={styles.errorBanner}>
            {errorMsg}
          </div>
        ) : null}

        {carts.map((cart) => {
          const subtotal = getTotal(cart);
          return (
            <div key={cart.store_id} className={styles.storeGroup}>
              <div className={styles.storeGroupHeader}>
                <div className={styles.storeGroupTitle}>
                  🏪{" "}
                  <Link
                    href={`/stores/${cart.store_id}`}
                    className={styles.storeGroupLink}
                  >
                    {cart.store_name}
                  </Link>
                </div>
                <button
                  className={styles.clearBtn}
                  onClick={() => handleClear(cart.store_id)}
                >
                  {t("clearAll")}
                </button>
              </div>

              {cart.items.map((item) => (
                <div key={item.product_id} className={styles.cartItem}>
                  <div className={styles.itemEmoji}>📦</div>

                  <div className={styles.itemInfo}>
                    <div className={styles.itemName}>{item.product_name}</div>
                    <div className={styles.itemPrice}>{t("priceEach", { price: item.price })}</div>
                  </div>

                  <div className={styles.qtyControls}>
                    <button
                      className={styles.qtyBtn}
                      onClick={() =>
                        item.quantity <= 1
                          ? handleRemove(cart.store_id, item.product_id)
                          : handleUpdateQty(
                              cart.store_id,
                              item.product_id,
                              item.quantity - 1
                            )
                      }
                    >
                      −
                    </button>
                    <span className={styles.qtyValue}>{item.quantity}</span>
                    <button
                      className={styles.qtyBtn}
                      onClick={() =>
                        handleUpdateQty(
                          cart.store_id,
                          item.product_id,
                          item.quantity + 1
                        )
                      }
                    >
                      +
                    </button>
                  </div>

                  <div className={styles.itemTotal}>
                    ₹{item.price * item.quantity}
                  </div>

                  <button
                    className={styles.removeBtn}
                    onClick={() => handleRemove(cart.store_id, item.product_id)}
                    aria-label={t("removeAria", { name: item.product_name })}
                  >
                    ✕
                  </button>
                </div>
              ))}

              <div className={styles.storeFooter}>
                <span className={styles.storeSubtotalValue}>
                  {t("subtotal", { value: subtotal })}
                </span>
                {renderCheckoutCta(cart.store_id, subtotal)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
