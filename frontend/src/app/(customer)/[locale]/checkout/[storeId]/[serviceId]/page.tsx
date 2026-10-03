"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { useCart } from "@/lib/CartContext";
import { apiErrorCode, apiErrorKey } from "@/lib/errors";
import { get } from "@/lib/api";
import { getCreditEligibility, type CreditEligibility } from "@/lib/credit";
import { placeOrder } from "@/lib/orders";
import { formatDeliveryEta } from "@/lib/deliveryEta";
import { WINDOW_META, formatDateLabel } from "@/lib/deliveryWindows";
import AddressPicker, { type PickerState } from "@/components/orders/AddressPicker";
import { DeliveryRouteMap } from "@/components/orders/DeliveryRouteMap";
import DeliveryModeSelector from "@/components/orders/DeliveryModeSelector";
import PaymentMethodPicker from "@/components/orders/PaymentMethodPicker";
import PriceComparison from "@/components/orders/PriceComparison";
import { formatAddress } from "@/lib/format-address";
import ReplaceAdjustmentsBanner from "@/components/orders/ReplaceAdjustmentsBanner";
import DeliveryTimePicker, {
  type PreferredWindowValue,
} from "@/components/orders/DeliveryTimePicker";
import { listStoreCredit } from "@/lib/returns";
import CourierExplainer from "@/components/orders/courier/CourierExplainer";
import RecipientFields, {
  isRecipientValid,
  type RecipientValue,
} from "@/components/orders/courier/RecipientFields";
import type { StoreCreditBalance } from "@/types";
import type { DeliveryMode, PaymentMethod, Store } from "@/types";
import styles from "./page.module.css";

export default function CheckoutPage() {
  const t = useTranslations("Checkout");
  const td = useTranslations("Order.delivery");
  const tErr = useTranslations("Errors");
  const locale = useLocale();
  const params = useParams<{ storeId: string; serviceId: string }>();
  const storeId = Number(params.storeId);
  const serviceId = Number(params.serviceId);
  // Store credit the seller owes this customer. Auto-applies unless unticked.
  const [storeCredit, setStoreCredit] = useState<StoreCreditBalance | null>(null);
  const [useStoreCredit, setUseStoreCredit] = useState(true);
  const router = useRouter();
  const { dbUser, token, loading: authLoading } = useAuth();
  const { carts, loading: cartLoading, refresh, getTotal } = useCart();

  const [addressId, setAddressId] = useState<number | null>(null);
  const [pickerState, setPickerState] = useState<PickerState>({
    selectedId: null,
    latitude: null,
    longitude: null,
    serviceable: false,
    zone: null,
    city: null,
    loading: true,
  });
  const [storeDetails, setStoreDetails] = useState<Store | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("upi");
  const [deliveryMode, setDeliveryMode] = useState<DeliveryMode>("door_delivery");
  const [preferredWindow, setPreferredWindow] = useState<PreferredWindowValue | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);
  const [creditStanding, setCreditStanding] = useState<CreditEligibility | null>(null);
  const [recipient, setRecipient] = useState<RecipientValue>({ name: "", phone: "" });
  const [storeLoadFailed, setStoreLoadFailed] = useState(false);
  // Bumped when the server says the address's zone changed (spec §8.5).
  const [zoneRecheck, setZoneRecheck] = useState(0);
  // Courier mode follows the picked address (spec §8.1). A plain value, not a
  // hook; computed here because the payment-method effect depends on it.
  const courierModeActive = deliveryMode !== "pickup" && pickerState.zone === "courier";

  useEffect(() => {
    if (!storeId || Number.isNaN(storeId)) return;
    get<Store>(`/api/v1/stores/${storeId}`)
      .then((s) => {
        setStoreDetails(s);
        setStoreLoadFailed(false);
      })
      .catch(() => {
        setStoreDetails(null);
        setStoreLoadFailed(true);
      });
    // zoneRecheck: a courier radius, toggle or payee changed mid-checkout, so
    // re-read courier_payment_methods along with the zones.
  }, [storeId, zoneRecheck]);

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

  // Keep the selected payment method valid for BOTH the delivery mode (cash is
  // door-only, pay-at-store is pickup-only) and what this store actually
  // accepts. A store whose seller has no UPI payee does not offer `upi` at
  // all, yet `upi` is the initial default — so this cannot just fall back to
  // "upi" the way it used to.
  useEffect(() => {
    if (courierModeActive) {
      const live = storeDetails?.courier_payment_methods;
      // Not loaded yet, or nothing live — leave it; the button explains.
      if (!live || live.length === 0) return;
      // Also moves a customer off `credit`, which courier never takes.
      if (!live.includes(paymentMethod)) setPaymentMethod(live[0]);
      return;
    }
    // `credit` is a per-customer entitlement and is deliberately absent from
    // the store's method list; never auto-correct away from it.
    if (paymentMethod === "credit") return;
    const accepted = storeDetails?.accepted_payment_methods;
    // Absent/empty means the store payload has not loaded — leave the
    // selection alone rather than bouncing it around during load.
    const storeAccepts = (m: PaymentMethod) =>
      !accepted || accepted.length === 0 || accepted.includes(m);
    const modeOk =
      !(deliveryMode === "pickup" && paymentMethod === "cash") &&
      !(deliveryMode === "door_delivery" && paymentMethod === "pay_at_store");
    if (modeOk && storeAccepts(paymentMethod)) return;
    const preference: PaymentMethod[] =
      deliveryMode === "pickup"
        ? ["upi", "pay_at_store", "net_banking"]
        : ["upi", "cash", "net_banking"];
    const next = preference.find(storeAccepts);
    if (next && next !== paymentMethod) setPaymentMethod(next);
  }, [
    courierModeActive,
    deliveryMode,
    paymentMethod,
    storeDetails?.accepted_payment_methods,
    storeDetails?.courier_payment_methods,
  ]);

  const cart = useMemo(
    () =>
      carts.find(
        (c) => c.store_id === storeId && c.service_id === serviceId,
      ),
    [carts, storeId, serviceId],
  );

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const balances = await listStoreCredit(token);
        if (cancelled) return;
        // Match on store_id, never the display name: a rename or a duplicate
        // store name would otherwise apply a different seller's credit.
        const match = balances.find(
          (b) => b.balance > 0 && b.store_id === storeId
        );
        setStoreCredit(match ?? null);
      } catch {
        // A failed lookup simply means no discount is offered — never a
        // confident "you have 0 credit".
        if (!cancelled) setStoreCredit(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, storeId]);

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

  const isPickup = deliveryMode === "pickup";
  const isCourier = courierModeActive;
  const apiMode: DeliveryMode = isPickup ? "pickup" : isCourier ? "courier" : "door_delivery";
  // null = the store payload hasn't loaded (or failed); [] = nothing live.
  const courierMethods = storeDetails?.courier_payment_methods ?? null;
  const courierBlocked =
    isCourier &&
    (!isRecipientValid(recipient) || courierMethods === null || courierMethods.length === 0);
  const pickupAvailable = !!storeDetails?.services.find((s) => s.id === serviceId)
    ?.pickup_enabled;
  const subtotal = getTotal(cart);
  const freeDeliveryThreshold = cart.free_delivery_threshold ?? 0;
  const baseFee = cart.delivery_fee ?? 0;
  const shortfall = Math.max(0, freeDeliveryThreshold - subtotal);
  // Courier: the charge is quoted by the store after the order (spec §9.2).
  const deliveryFee = isPickup || isCourier ? 0 : shortfall > 0 ? baseFee : 0;
  const feeApplies = deliveryFee > 0;
  const tax = 0;
  const grossTotal = subtotal + deliveryFee + tax;
  const creditApplied =
    useStoreCredit && storeCredit
      ? Math.min(storeCredit.balance, grossTotal)
      : 0;
  // `total` stays what the customer pays, which is what the button and the
  // postpaid-credit eligibility check below both care about.
  const total = Number((grossTotal - creditApplied).toFixed(2));
  const hasCredit = creditStanding != null && creditStanding.credit_limit > 0;
  const creditEligible = hasCredit && total <= creditStanding!.available;
  const creditSelectedButBlocked = paymentMethod === "credit" && !creditEligible;
  const etaLabel =
    cart.delivery_eta_min_minutes != null && cart.delivery_eta_max_minutes != null
      ? formatDeliveryEta(cart.delivery_eta_min_minutes, cart.delivery_eta_max_minutes)
      : null;

  const onPlaceOrder = async () => {
    if (!token) return;
    if (!isPickup && addressId === null) return;
    if (paymentMethod === "credit" && !creditEligible) {
      setError(t("errCreditUnavailable"));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const placedOrder = await placeOrder(token, {
        customerAddressId: isPickup ? null : addressId,
        storeId,
        serviceId,
        paymentMethod,
        deliveryMode: apiMode,
        // Courier orders take no preferred window (422 preferred_window_not_allowed).
        preferredDeliveryDate: isCourier ? null : preferredWindow?.date ?? null,
        preferredDeliveryWindow: isCourier ? null : preferredWindow?.window ?? null,
        // Only ever true when the page actually displayed the discount, so
        // the quoted total and the charged amount cannot diverge.
        applyStoreCredit: useStoreCredit && Boolean(storeCredit),
        recipientName: isCourier ? recipient.name.trim() : null,
        recipientPhone: isCourier ? recipient.phone : null,
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
      // The pause 409 carries a structured dict detail. This pre-match is kept
      // because `store_paused`/`service_paused` also need the /cart redirect
      // below; apiErrorKey() itself now reads object-shaped details via
      // apiErrorCode(), so it no longer collapses every 409 to "conflict".
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
      const zoneCode = apiErrorCode(e);
      if (
        zoneCode === "address_within_local_area" ||
        zoneCode === "outside_courier_area" ||
        zoneCode === "courier_unavailable" ||
        zoneCode === "courier_destination_unsupported" ||
        zoneCode === "upi_unavailable" ||
        zoneCode === "bank_transfer_unavailable"
      ) {
        // The zone or the store's payees changed under the page: re-classify
        // the addresses and re-read the live payees, so the page switches
        // mode on its own while the message explains why.
        setZoneRecheck((n) => n + 1);
      }
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
          <DeliveryModeSelector
            value={deliveryMode}
            onChange={setDeliveryMode}
            pickupAvailable={pickupAvailable}
          />
        </section>

        {!isPickup && (
          <>
            <section className={styles.section}>
              <h2 className={styles.sectionTitle}>{t("deliveryAddress")}</h2>
              <AddressPicker
                value={addressId}
                onChange={setAddressId}
                storeId={storeId}
                serviceId={serviceId}
                recheckKey={zoneRecheck}
                onStateChange={setPickerState}
              />
              {/* No route for courier: meaningless at that distance, and it
                  would cost a Directions call (spec §8.2). */}
              {!isCourier &&
                pickerState.serviceable &&
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
            {isCourier && (
              <>
                <CourierExplainer storeName={cart.store_name} city={pickerState.city} />
                <section className={styles.section}>
                  <RecipientFields value={recipient} onChange={setRecipient} />
                </section>
              </>
            )}
          </>
        )}

        {isPickup && storeDetails && (
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>{t("collectAt")}</h2>
            <div className={styles.pickupCard}>
              <strong>{storeDetails.name}</strong>
              <span>{formatAddress(storeDetails.address)}</span>
            </div>
          </section>
        )}

        <section className={styles.section}>
          <PaymentMethodPicker
            value={paymentMethod}
            onChange={setPaymentMethod}
            deliveryMode={apiMode}
            courierMethods={courierMethods ?? undefined}
            acceptedMethods={storeDetails?.accepted_payment_methods}
            upiPayee={storeDetails?.upi_payee ?? null}
            previewAmount={total}
            credit={
              hasCredit
                ? { available: creditStanding!.available, eligible: creditEligible }
                : null
            }
          />
        </section>

        {!isCourier && (
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>{td("preferredTitle")}</h2>
            <p className={styles.shortfallNote}>{td("preferredHint")}</p>
            <DeliveryTimePicker value={preferredWindow} onChange={setPreferredWindow} />
          </section>
        )}

        <section className={styles.summary}>
          <div className={styles.summaryRow}>
            <span>{t("subtotal")}</span>
            <span>₹{subtotal}</span>
          </div>
          <div className={styles.summaryRow}>
            <span>{t("deliveryFee")}</span>
            <span>{isCourier ? t("courier.chargeQuoted") : `₹${deliveryFee.toFixed(2)}`}</span>
          </div>
          <div className={styles.summaryRow}>
            <span>{t("tax")}</span>
            <span>₹{tax}</span>
          </div>
          {!isCourier && etaLabel && (
            <div className={styles.summaryRow}>
              <span>{t("estimatedDelivery")}</span>
              <span>{etaLabel}</span>
            </div>
          )}
          {/* A window picked before switching to a courier address is never
              sent, so it must not be shown either. */}
          {!isCourier && preferredWindow && (
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
          {storeCredit && storeCredit.balance > 0 && (
            <div className={styles.summaryRow}>
              <label className={styles.creditToggle}>
                <input
                  type="checkbox"
                  checked={useStoreCredit}
                  onChange={(e) => setUseStoreCredit(e.target.checked)}
                />
                <span>
                  {t("storeCreditLabel", {
                    balance: storeCredit.balance.toFixed(2),
                  })}
                </span>
              </label>
              <span>−₹{creditApplied.toFixed(2)}</span>
            </div>
          )}
          <div className={`${styles.summaryRow} ${styles.summaryTotal}`}>
            <span>{isCourier ? t("courier.totalSoFar") : t("total")}</span>
            <span>{isCourier ? t("courier.totalPlusCourier", { total }) : `₹${total}`}</span>
          </div>
        </section>

        {!isPickup && !isCourier && (
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
        )}

        {error && <div className={styles.error} role="alert">{error}</div>}

        {feeApplies && !isCourier && (
          <p className={styles.shortfallNote} role="status">
            {t("minOrderShortfall", { amount: shortfall })}
          </p>
        )}

        <button
          className={styles.placeBtn}
          onClick={onPlaceOrder}
          disabled={
            submitting ||
            creditSelectedButBlocked ||
            courierBlocked ||
            (!isPickup &&
              (pickerState.selectedId === null ||
                pickerState.loading ||
                !pickerState.serviceable))
          }
        >
          {submitting
            ? t("placing")
            : !isPickup && pickerState.loading
              ? t("checkingDeliveryArea")
              : isCourier
                ? t("courier.placeOrder")
                : t("placeOrder", { total })}
        </button>
        {isCourier && (
          <p className={styles.shortfallNote} role="status">
            {storeLoadFailed
              ? t("courier.storeLoadError")
              : courierMethods === null
                ? t("loading")
                : courierMethods.length === 0
                  ? t("courier.noPayee")
                  : !isRecipientValid(recipient)
                    ? t("courier.recipientNeeded")
                    : t("courier.nothingToPay")}
          </p>
        )}
      </div>
    </div>
  );
}
