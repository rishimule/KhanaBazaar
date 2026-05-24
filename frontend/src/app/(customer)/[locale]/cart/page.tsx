"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { useCart } from "@/lib/CartContext";
import { apiErrorKey } from "@/lib/errors";
import type { Cart } from "@/types";
import ReplaceAdjustmentsBanner from "@/components/orders/ReplaceAdjustmentsBanner";
import styles from "./page.module.css";

interface StoreGroup {
  store_id: number;
  store_name: string;
  subBaskets: Cart[];
}

function groupByStore(carts: Cart[]): StoreGroup[] {
  const byId = new Map<number, StoreGroup>();
  for (const c of carts) {
    let g = byId.get(c.store_id);
    if (!g) {
      g = { store_id: c.store_id, store_name: c.store_name, subBaskets: [] };
      byId.set(c.store_id, g);
    }
    g.subBaskets.push(c);
  }
  for (const g of byId.values()) {
    g.subBaskets.sort((a, b) => a.service_id - b.service_id);
  }
  return [...byId.values()];
}

export default function CartPage() {
  const t = useTranslations("Cart");
  const tErr = useTranslations("Errors");
  const { carts, removeItem, updateQty, clearSubBasket, getTotal } = useCart();
  const { dbUser } = useAuth();
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const storeGroups = useMemo(() => groupByStore(carts), [carts]);

  const handleClear = async (storeId: number, serviceId: number) => {
    setErrorMsg(null);
    try {
      await clearSubBasket(storeId, serviceId);
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

  const handleRemove = async (
    storeId: number,
    serviceId: number,
    productId: number,
  ) => {
    setErrorMsg(null);
    try {
      await removeItem(storeId, serviceId, productId);
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
    serviceId: number,
    productId: number,
    qty: number,
  ) => {
    setErrorMsg(null);
    try {
      await updateQty(storeId, serviceId, productId, qty);
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

  const renderCheckoutCta = (
    storeId: number,
    serviceId: number,
    serviceName: string,
    subtotal: number,
  ) => {
    if (!dbUser) {
      return (
        <Link
          href={`/login?next=/checkout/${storeId}/${serviceId}`}
          className={styles.checkoutBtn}
        >
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
      <Link
        href={`/checkout/${storeId}/${serviceId}`}
        className={styles.checkoutBtn}
      >
        {t("checkoutCta", { subtotal, service: serviceName })}
      </Link>
    );
  };

  const totalItems = carts.reduce(
    (sum, c) => sum + c.items.reduce((s, i) => s + i.quantity, 0),
    0,
  );

  return (
    <div className={styles.page}>
      <div className={styles.pageInner}>
        <ReplaceAdjustmentsBanner />
        <div className={styles.header}>
          <h1 className={styles.title}>
            {t("yourLabel")}{" "}
            <span className={styles.titleAccent}>{t("cartLabel")}</span>
          </h1>
          <p className={styles.subtitle}>
            {t("summary", { stores: storeGroups.length, items: totalItems })}
          </p>
        </div>

        {errorMsg ? (
          <div role="alert" className={styles.errorBanner}>
            {errorMsg}
          </div>
        ) : null}

        {storeGroups.map((group) => (
          <div key={group.store_id} className={styles.storeGroup}>
            <div className={styles.storeGroupHeader}>
              <div className={styles.storeGroupTitle}>
                🏪{" "}
                <Link
                  href={`/stores/${group.store_id}`}
                  className={styles.storeGroupLink}
                >
                  {group.store_name}
                </Link>
              </div>
            </div>

            {group.subBaskets.map((cart) => {
              const subtotal = getTotal(cart);
              const showServiceHeader = group.subBaskets.length > 1;
              return (
                <div key={cart.service_id} className={styles.serviceSection}>
                  {showServiceHeader && (
                    <div className={styles.serviceHeader}>
                      <span className={styles.serviceName}>
                        {cart.service_name}
                      </span>
                      <button
                        className={styles.clearBtn}
                        onClick={() =>
                          handleClear(cart.store_id, cart.service_id)
                        }
                      >
                        {t("clearAll")}
                      </button>
                    </div>
                  )}
                  {!showServiceHeader && (
                    <div className={styles.serviceHeader}>
                      <span />
                      <button
                        className={styles.clearBtn}
                        onClick={() =>
                          handleClear(cart.store_id, cart.service_id)
                        }
                      >
                        {t("clearAll")}
                      </button>
                    </div>
                  )}

                  {cart.items.map((item) => (
                    <div key={item.product_id} className={styles.cartItem}>
                      <div className={styles.itemEmoji}>📦</div>

                      <div className={styles.itemInfo}>
                        <div className={styles.itemName}>{item.product_name}</div>
                        <div className={styles.itemPrice}>
                          {t("priceEach", { price: item.price })}
                        </div>
                      </div>

                      <div className={styles.qtyControls}>
                        <button
                          className={styles.qtyBtn}
                          onClick={() =>
                            item.quantity <= 1
                              ? handleRemove(
                                  cart.store_id,
                                  cart.service_id,
                                  item.product_id,
                                )
                              : handleUpdateQty(
                                  cart.store_id,
                                  cart.service_id,
                                  item.product_id,
                                  item.quantity - 1,
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
                              cart.service_id,
                              item.product_id,
                              item.quantity + 1,
                            )
                          }
                        >
                          +
                        </button>
                      </div>

                      <div className={styles.itemTotal}>
                        ₹{(item.price * item.quantity).toFixed(2)}
                      </div>

                      <button
                        className={styles.removeBtn}
                        onClick={() =>
                          handleRemove(
                            cart.store_id,
                            cart.service_id,
                            item.product_id,
                          )
                        }
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
                    {renderCheckoutCta(
                      cart.store_id,
                      cart.service_id,
                      cart.service_name,
                      subtotal,
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
