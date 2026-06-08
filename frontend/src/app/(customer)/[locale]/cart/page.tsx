"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { useCart } from "@/lib/CartContext";
import { get } from "@/lib/api";
import { apiErrorKey } from "@/lib/errors";
import type { Cart, Store } from "@/types";
import ReplaceAdjustmentsBanner from "@/components/orders/ReplaceAdjustmentsBanner";
import CartAddedToast from "@/components/orders/CartAddedToast";
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
  const { dbUser, token } = useAuth();
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [storesById, setStoresById] = useState<Record<number, Store>>({});

  const storeGroups = useMemo(() => groupByStore(carts), [carts]);

  // Fetch the stores backing the cart sub-baskets so we can surface pause
  // ("Closed") state and disable checkout before the customer hits a 409.
  const storeIdsKey = useMemo(
    () => Array.from(new Set(carts.map((c) => c.store_id))).sort().join(","),
    [carts],
  );
  useEffect(() => {
    const ids = storeIdsKey ? storeIdsKey.split(",").map(Number) : [];
    if (ids.length === 0) return;
    let cancelled = false;
    Promise.all(
      ids.map((id) =>
        get<Store>(`/api/v1/stores/${id}`, token).catch(() => null),
      ),
    ).then((results) => {
      if (cancelled) return;
      const map: Record<number, Store> = {};
      for (const s of results) if (s) map[s.id] = s;
      setStoresById(map);
    });
    return () => {
      cancelled = true;
    };
  }, [storeIdsKey, token]);

  const isStoreServicePaused = (storeId: number, serviceId: number): boolean => {
    const store = storesById[storeId];
    if (!store) return false;
    if (store.is_paused) return true;
    return store.services.find((s) => s.id === serviceId)?.is_paused ?? false;
  };

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
    freeDeliveryThreshold: number,
    deliveryFee: number,
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
    if (isStoreServicePaused(storeId, serviceId)) {
      return (
        <div className={styles.shortfallBanner} role="status">
          {t("storePausedBanner")}
          <span className={styles.checkoutBtn} aria-disabled>
            {t("checkoutCta", { subtotal, service: serviceName })}
          </span>
        </div>
      );
    }
    const shortfall = Math.max(0, freeDeliveryThreshold - subtotal);
    const feeApplies = deliveryFee > 0 && shortfall > 0;
    return (
      <>
        {feeApplies && (
          <div className={styles.shortfallBanner} role="status">
            {t("minOrderShortfall", { amount: shortfall, service: serviceName })}
          </div>
        )}
        <Link
          href={`/checkout/${storeId}/${serviceId}`}
          className={styles.checkoutBtn}
        >
          {t("checkoutCta", { subtotal, service: serviceName })}
        </Link>
      </>
    );
  };

  const totalItems = carts.reduce(
    (sum, c) => sum + c.items.reduce((s, i) => s + i.quantity, 0),
    0,
  );

  return (
    <div className={styles.page}>
      <div className={styles.pageInner}>
        <CartAddedToast />
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
                    {subtotal < (cart.free_delivery_threshold ?? 0) &&
                      (cart.delivery_fee ?? 0) > 0 && (
                        <span className={styles.storeSubtotalValue}>
                          {t("deliveryFee")}: ₹{(cart.delivery_fee ?? 0).toFixed(2)}
                        </span>
                      )}
                    {renderCheckoutCta(
                      cart.store_id,
                      cart.service_id,
                      cart.service_name,
                      subtotal,
                      cart.free_delivery_threshold ?? 0,
                      cart.delivery_fee ?? 0,
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
