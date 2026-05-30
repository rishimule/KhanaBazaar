"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { useCart } from "@/lib/CartContext";
import { apiErrorKey } from "@/lib/errors";
import { get } from "@/lib/api";
import { placeOrder } from "@/lib/orders";
import { formatDeliveryEta } from "@/lib/deliveryEta";
import AddressPicker, { type PickerState } from "@/components/orders/AddressPicker";
import { DeliveryRouteMap } from "@/components/orders/DeliveryRouteMap";
import PaymentMethodPicker from "@/components/orders/PaymentMethodPicker";
import PriceComparison from "@/components/orders/PriceComparison";
import ReplaceAdjustmentsBanner from "@/components/orders/ReplaceAdjustmentsBanner";
import type { PaymentMethod, Store } from "@/types";
import styles from "./page.module.css";

export default function CheckoutPage() {
  const t = useTranslations("Checkout");
  const tErr = useTranslations("Errors");
  const params = useParams<{ storeId: string; serviceId: string }>();
  const storeId = Number(params.storeId);
  const serviceId = Number(params.serviceId);
  const router = useRouter();
  const { dbUser, token, loading: authLoading } = useAuth();
  const { carts, loading: cartLoading, refresh, getTotal } = useCart();

  const [addressId, setAddressId] = useState<number | null>(null);
  const [pickerState, setPickerState] = useState<PickerState>({
    selectedId: null,
    latitude: null,
    longitude: null,
    serviceable: false,
    loading: true,
  });
  const [storeDetails, setStoreDetails] = useState<Store | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("upi");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!storeId || Number.isNaN(storeId)) return;
    get<Store>(`/api/v1/stores/${storeId}`)
      .then(setStoreDetails)
      .catch(() => setStoreDetails(null));
  }, [storeId]);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeId, serviceId]);

  const cart = useMemo(
    () =>
      carts.find(
        (c) => c.store_id === storeId && c.service_id === serviceId,
      ),
    [carts, storeId, serviceId],
  );

  const isCustomer = dbUser?.role === "customer";

  useEffect(() => {
    if (!authLoading && !cartLoading && isCustomer && !cart) {
      router.replace("/cart");
    }
  }, [authLoading, cartLoading, isCustomer, cart, router]);

  if (authLoading || cartLoading) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <p className={styles.loadingText}>{t("loading")}</p>
        </div>
      </div>
    );
  }

  if (!dbUser) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <p className={styles.loadingText}>
            {t.rich("loginPrompt", {
              login: (chunks) => (
                <Link href={`/login?next=/checkout/${storeId}/${serviceId}`}>
                  {chunks}
                </Link>
              ),
            })}
          </p>
        </div>
      </div>
    );
  }

  if (!isCustomer) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <p className={styles.loadingText}>{t("customerLoginRequired")}</p>
        </div>
      </div>
    );
  }

  if (!cart) {
    return null;
  }

  const subtotal = getTotal(cart);
  const deliveryFee = 0;
  const tax = 0;
  const total = subtotal + deliveryFee + tax;
  const minOrderValue = cart.min_order_value ?? 0;
  const shortfall = Math.max(0, minOrderValue - subtotal);
  const etaLabel =
    cart.delivery_eta_min_minutes != null && cart.delivery_eta_max_minutes != null
      ? formatDeliveryEta(cart.delivery_eta_min_minutes, cart.delivery_eta_max_minutes)
      : null;

  const onPlaceOrder = async () => {
    if (!token || addressId === null) return;
    setSubmitting(true);
    setError(null);
    try {
      await placeOrder(token, {
        customerAddressId: addressId,
        storeId,
        serviceId,
        paymentMethod,
      });
      // Placing the order clears this sub-basket server-side. Refresh cart
      // state so the navbar count + cart pages reflect it immediately instead
      // of after a manual reload. Guarded: the order already succeeded, so a
      // refresh failure must not surface as a place-order error.
      try {
        await refresh();
      } catch {
        /* non-fatal */
      }
      router.push("/account/orders?placed=1");
    } catch (e) {
      // The minimum-order 409 carries a structured dict detail, so it must be
      // matched before apiErrorKey() (which maps every 409 to "conflict").
      const rawDetail = (e as { detail?: unknown })?.detail;
      const structured =
        rawDetail && typeof rawDetail === "object" && "detail" in rawDetail
          ? (rawDetail as { detail: unknown; shortfall?: number })
          : null;
      if (structured?.detail === "below_minimum_order_value") {
        setError(t("minOrderShortfall", { amount: structured.shortfall ?? 0 }));
        return;
      }
      const key = apiErrorKey(e);
      if (key) {
        setError(tErr(key.replace(/^Errors\./, "")));
      } else if (typeof rawDetail === "string") {
        setError(rawDetail);
      } else if (structured) {
        setError(String(structured.detail));
      } else {
        setError(t("errPlaceOrder"));
      }
      if (
        key === "Errors.service_unavailable" ||
        key === "Errors.service_mismatch"
      ) {
        router.push("/cart");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.pageInner}>
        <div className={styles.header}>
          <Link href="/cart" className={styles.backLink}>
            {t("backToCart")}
          </Link>
          <h1 className={styles.title}>
            {t("title", { store: cart.store_name })} · {cart.service_name}
          </h1>
        </div>

        <ReplaceAdjustmentsBanner />

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>{t("items")}</h2>
          <ul className={styles.itemList}>
            {cart.items.map((item) => (
              <li key={item.product_id} className={styles.itemRow}>
                <span className={styles.itemName}>{item.product_name}</span>
                <span className={styles.itemQty}>× {item.quantity}</span>
                <span className={styles.itemPrice}>
                  ₹{(item.price * item.quantity).toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>{t("deliveryAddress")}</h2>
          <AddressPicker
            value={addressId}
            onChange={setAddressId}
            storeId={storeId}
            onStateChange={setPickerState}
          />
          {pickerState.serviceable &&
            pickerState.latitude != null &&
            pickerState.longitude != null &&
            storeDetails?.address.latitude != null &&
            storeDetails?.address.longitude != null && (
              <div className={styles.routeMap}>
                <DeliveryRouteMap
                  store={{
                    lat: storeDetails.address.latitude,
                    lng: storeDetails.address.longitude,
                    label: storeDetails.name,
                  }}
                  customer={{
                    lat: pickerState.latitude,
                    lng: pickerState.longitude,
                    label: "Your address",
                  }}
                />
              </div>
            )}
        </section>

        <section className={styles.section}>
          <PaymentMethodPicker
            value={paymentMethod}
            onChange={setPaymentMethod}
          />
        </section>

        <section className={styles.summary}>
          <div className={styles.summaryRow}>
            <span>{t("subtotal")}</span>
            <span>₹{subtotal}</span>
          </div>
          <div className={styles.summaryRow}>
            <span>{t("deliveryFee")}</span>
            <span>₹{deliveryFee}</span>
          </div>
          <div className={styles.summaryRow}>
            <span>{t("tax")}</span>
            <span>₹{tax}</span>
          </div>
          {etaLabel && (
            <div className={styles.summaryRow}>
              <span>{t("estimatedDelivery")}</span>
              <span>{etaLabel}</span>
            </div>
          )}
          <div className={`${styles.summaryRow} ${styles.summaryTotal}`}>
            <span>{t("total")}</span>
            <span>₹{total}</span>
          </div>
        </section>

        <PriceComparison
          sourceStoreId={storeId}
          sourceStoreName={cart.store_name}
          serviceId={serviceId}
          serviceName={cart.service_name}
          customerAddressId={pickerState.selectedId}
          serviceable={pickerState.serviceable}
          pickerLoading={pickerState.loading}
          cart={cart}
        />

        {error && <div className={styles.error}>{error}</div>}

        {shortfall > 0 && (
          <p className={styles.shortfallNote} role="status">
            {t("minOrderShortfall", { amount: shortfall })}
          </p>
        )}

        <button
          className={styles.placeBtn}
          onClick={onPlaceOrder}
          disabled={
            submitting ||
            pickerState.selectedId === null ||
            pickerState.loading ||
            !pickerState.serviceable ||
            shortfall > 0
          }
        >
          {submitting
            ? t("placing")
            : pickerState.loading
              ? t("checkingDeliveryArea")
              : t("placeOrder", { total })}
        </button>
      </div>
    </div>
  );
}
