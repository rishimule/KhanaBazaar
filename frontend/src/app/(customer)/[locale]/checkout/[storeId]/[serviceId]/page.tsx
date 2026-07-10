"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { useCart } from "@/lib/CartContext";
import { apiErrorKey } from "@/lib/errors";
import { get } from "@/lib/api";
import { getCreditEligibility, type CreditEligibility } from "@/lib/credit";
import { placeOrder } from "@/lib/orders";
import { formatDeliveryEta } from "@/lib/deliveryEta";
import { WINDOW_META, formatDateLabel } from "@/lib/deliveryWindows";
import AddressPicker, { type PickerState } from "@/components/orders/AddressPicker";
import { DeliveryRouteMap } from "@/components/orders/DeliveryRouteMap";
import PaymentMethodPicker from "@/components/orders/PaymentMethodPicker";
import PriceComparison from "@/components/orders/PriceComparison";
import ReplaceAdjustmentsBanner from "@/components/orders/ReplaceAdjustmentsBanner";
import DeliveryTimePicker, {
  type PreferredWindowValue,
} from "@/components/orders/DeliveryTimePicker";
import type { PaymentMethod, Store } from "@/types";
import styles from "./page.module.css";

export default function CheckoutPage() {
  const t = useTranslations("Checkout");
  const td = useTranslations("Order.delivery");
  const tErr = useTranslations("Errors");
  const locale = useLocale();
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
  const [preferredWindow, setPreferredWindow] = useState<PreferredWindowValue | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);
  const [creditStanding, setCreditStanding] = useState<CreditEligibility | null>(null);

  useEffect(() => {
    if (!storeId || Number.isNaN(storeId)) return;
    get<Store>(`/api/v1/stores/${storeId}`)
      .then(setStoreDetails)
      .catch(() => setStoreDetails(null));
  }, [storeId]);

  // Fetch the customer's credit standing at this store once (total=0 just reads
  // the account); eligibility vs the live cart total is computed client-side.
  useEffect(() => {
    if (!token || !storeId || Number.isNaN(storeId)) return;
    getCreditEligibility(token, storeId, 0)
      .then(setCreditStanding)
      .catch(() => setCreditStanding(null));
  }, [token, storeId]);

  useEffect(() => {
    setSwitching(false);
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
    if (!authLoading && !cartLoading && isCustomer && !cart && !switching) {
      router.replace("/cart");
    }
  }, [authLoading, cartLoading, isCustomer, cart, switching, router]);

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
  const freeDeliveryThreshold = cart.free_delivery_threshold ?? 0;
  const baseFee = cart.delivery_fee ?? 0;
  const shortfall = Math.max(0, freeDeliveryThreshold - subtotal);
  const deliveryFee = shortfall > 0 ? baseFee : 0;
  const feeApplies = deliveryFee > 0;
  const tax = 0;
  const total = subtotal + deliveryFee + tax;
  const hasCredit = creditStanding != null && creditStanding.credit_limit > 0;
  const creditEligible = hasCredit && total <= creditStanding!.available;
  const creditSelectedButBlocked = paymentMethod === "credit" && !creditEligible;
  const etaLabel =
    cart.delivery_eta_min_minutes != null && cart.delivery_eta_max_minutes != null
      ? formatDeliveryEta(cart.delivery_eta_min_minutes, cart.delivery_eta_max_minutes)
      : null;

  const onPlaceOrder = async () => {
    if (!token || addressId === null) return;
    if (paymentMethod === "credit" && !creditEligible) {
      setError(t("errCreditUnavailable"));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const placedOrder = await placeOrder(token, {
        customerAddressId: addressId,
        storeId,
        serviceId,
        paymentMethod,
        preferredDeliveryDate: preferredWindow?.date ?? null,
        preferredDeliveryWindow: preferredWindow?.window ?? null,
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
      router.push(`/order-confirmed/${placedOrder.id}`);
    } catch (e) {
      // The pause 409 carries a structured dict detail, so it must be
      // matched before apiErrorKey() (which maps every 409 to "conflict").
      const rawDetail = (e as { detail?: unknown })?.detail;
      const structured =
        rawDetail && typeof rawDetail === "object" && "detail" in rawDetail
          ? (rawDetail as { detail: unknown })
          : null;
      if (
        structured?.detail === "store_paused" ||
        structured?.detail === "service_paused"
      ) {
        setError(tErr("store_paused"));
        router.push("/cart");
        return;
      }
      const errCode =
        rawDetail && typeof rawDetail === "object" && "error" in rawDetail
          ? (rawDetail as { error?: string }).error
          : null;
      if (errCode === "insufficient_credit" || errCode === "credit_not_available") {
        setError(t("errCreditUnavailable"));
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
            credit={
              hasCredit
                ? { available: creditStanding!.available, eligible: creditEligible }
                : null
            }
          />
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>{td("preferredTitle")}</h2>
          <p className={styles.shortfallNote}>{td("preferredHint")}</p>
          <DeliveryTimePicker value={preferredWindow} onChange={setPreferredWindow} />
        </section>

        <section className={styles.summary}>
          <div className={styles.summaryRow}>
            <span>{t("subtotal")}</span>
            <span>₹{subtotal}</span>
          </div>
          <div className={styles.summaryRow}>
            <span>{t("deliveryFee")}</span>
            <span>₹{deliveryFee.toFixed(2)}</span>
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
          {preferredWindow && (
            <div className={styles.summaryRow}>
              <span>{td("requested")}</span>
              <span>
                {formatDateLabel(preferredWindow.date, locale)} ·{" "}
                {td(
                  preferredWindow.window === "morning"
                    ? "windowMorning"
                    : preferredWindow.window === "afternoon"
                      ? "windowAfternoon"
                      : "windowEvening",
                )}{" "}
                ({WINDOW_META[preferredWindow.window].hours})
              </span>
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
          onSwitchStart={() => setSwitching(true)}
        />

        {error && <div className={styles.error} role="alert">{error}</div>}

        {feeApplies && (
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
            creditSelectedButBlocked
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
