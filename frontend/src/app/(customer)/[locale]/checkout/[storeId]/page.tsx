"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { useCart } from "@/lib/CartContext";
import { apiErrorKey } from "@/lib/errors";
import { placeOrder } from "@/lib/orders";
import AddressPicker from "@/components/orders/AddressPicker";
import PaymentMethodPicker from "@/components/orders/PaymentMethodPicker";
import type { PaymentMethod } from "@/types";
import styles from "./page.module.css";

export default function CheckoutPage() {
  const t = useTranslations("Checkout");
  const tErr = useTranslations("Errors");
  const params = useParams<{ storeId: string }>();
  const storeId = Number(params.storeId);
  const router = useRouter();
  const { dbUser, token, loading: authLoading } = useAuth();
  const { carts, loading: cartLoading, refresh, getTotal } = useCart();

  const [addressId, setAddressId] = useState<number | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("upi");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeId]);

  const cart = useMemo(
    () => carts.find((c) => c.store_id === storeId),
    [carts, storeId]
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
              login: () => (
                <Link href={`/login?next=/checkout/${storeId}`}>{t("loginLink")}</Link>
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

  const onPlaceOrder = async () => {
    if (!token || addressId === null) return;
    setSubmitting(true);
    setError(null);
    try {
      await placeOrder(token, {
        customerAddressId: addressId,
        storeId,
        paymentMethod,
      });
      router.push("/account/orders?placed=1");
    } catch (e) {
      const key = apiErrorKey(e);
      if (key) {
        setError(tErr(key.replace(/^Errors\./, "")));
      } else {
        const detail = (e as { detail?: unknown })?.detail;
        if (typeof detail === "string") {
          setError(detail);
        } else if (detail && typeof detail === "object" && "detail" in detail) {
          setError(String((detail as { detail: unknown }).detail));
        } else {
          setError(t("errPlaceOrder"));
        }
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
          <h1 className={styles.title}>{t("title", { store: cart.store_name })}</h1>
        </div>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>{t("items")}</h2>
          <ul className={styles.itemList}>
            {cart.items.map((item) => (
              <li key={item.product_id} className={styles.itemRow}>
                <span className={styles.itemName}>{item.product_name}</span>
                <span className={styles.itemQty}>× {item.quantity}</span>
                <span className={styles.itemPrice}>₹{item.price * item.quantity}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>{t("deliveryAddress")}</h2>
          <AddressPicker value={addressId} onChange={setAddressId} />
        </section>

        <section className={styles.section}>
          <PaymentMethodPicker value={paymentMethod} onChange={setPaymentMethod} />
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
          <div className={`${styles.summaryRow} ${styles.summaryTotal}`}>
            <span>{t("total")}</span>
            <span>₹{total}</span>
          </div>
        </section>

        {error && <div className={styles.error}>{error}</div>}

        <button
          className={styles.placeBtn}
          onClick={onPlaceOrder}
          disabled={submitting || addressId === null}
        >
          {submitting ? t("placing") : t("placeOrder", { total })}
        </button>
      </div>
    </div>
  );
}
