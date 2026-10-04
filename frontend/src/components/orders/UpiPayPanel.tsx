"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { get } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { claimUpiPayment } from "@/lib/orders";
import { netPayable } from "@/lib/upi";
import UpiQrBlock from "@/components/orders/UpiQrBlock";
import type { Order, Store } from "@/types";
import styles from "./UpiPayPanel.module.css";

interface Props {
  order: Order;
  onChange: (next: Order) => void;
}

/**
 * Scan-and-pay panel for UPI orders. Self-gating: renders nothing unless the
 * order is UPI, the payment is still pending, and the store's seller has a live
 * payee — so both the order-confirmed and order-detail pages can mount it
 * unconditionally.
 *
 * The QR is generated from the seller's VPA. The seller's own uploaded QR image
 * is deliberately never shown here: its encoded payee is unreadable to us, so
 * displaying it would put a second, unapproved payee in front of the customer.
 */
export default function UpiPayPanel({ order, onChange }: Props) {
  const t = useTranslations("UpiPay");
  const { token } = useAuth();
  const [payee, setPayee] = useState<NonNullable<Store["upi_payee"]> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Courier orders pay through CourierPayPanel once the quote is accepted
  // (UPI or bank tabs); this panel is for local UPI orders only.
  const isUpiPending =
    order.delivery_mode !== "courier" &&
    order.payment.method === "upi" &&
    order.payment.status === "pending";

  useEffect(() => {
    if (!isUpiPending) return;
    let cancelled = false;
    get<Store>(`/api/v1/stores/${order.store_id}`)
      .then((s) => {
        if (!cancelled) setPayee(s.upi_payee ?? null);
      })
      .catch(() => {
        if (!cancelled) setPayee(null);
      });
    return () => {
      cancelled = true;
    };
  }, [isUpiPending, order.store_id]);

  if (!isUpiPending || !payee) return null;

  // The NET figure. `order.total` is the gross goods cost and `payment.amount`
  // is gross too — billing either would tell a customer holding store credit to
  // overpay by exactly their balance.
  const amount = netPayable(order);
  const claimed = order.payment.customer_claimed_at;

  async function claim() {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      onChange(await claimUpiPayment(token, order.id));
    } catch {
      setError(t("claimFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.panel} aria-labelledby="upi-pay-title">
      <h2 id="upi-pay-title" className={styles.title}>
        {t("title", { amount: amount.toFixed(2) })}
      </h2>
      <p className={styles.payee}>{t("payTo", { name: payee.display_name })}</p>

      <UpiQrBlock
        vpa={payee.vpa}
        payeeName={payee.display_name}
        amount={amount}
        orderId={order.id}
        onError={setError}
      />

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {claimed ? (
        <p className={styles.claimed} role="status">
          {t("claimedAt", { when: new Date(claimed).toLocaleString("en-IN") })}
        </p>
      ) : (
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy}
          onClick={claim}
        >
          {t("ivePaid")}
        </button>
      )}
      <p className={styles.disclaimer}>{t("disclaimer")}</p>
    </section>
  );
}
