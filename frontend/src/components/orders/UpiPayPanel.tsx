"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { QRCodeSVG } from "qrcode.react";

import { get } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { claimUpiPayment } from "@/lib/orders";
import { buildUpiUri, isLikelyIOS, netPayable } from "@/lib/upi";
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
  const [copied, setCopied] = useState(false);
  const [ios, setIos] = useState(false);

  const isUpiPending =
    order.payment.method === "upi" && order.payment.status === "pending";

  // Resolved in an effect rather than during render: the UA is unavailable
  // server-side, and branching on it mid-render risks a hydration mismatch.
  useEffect(() => setIos(isLikelyIOS()), []);

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
  const uri = buildUpiUri({
    vpa: payee.vpa,
    payeeName: payee.display_name,
    amount,
    orderId: order.id,
  });
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

  async function copyVpa() {
    try {
      await navigator.clipboard.writeText(payee!.vpa);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setError(t("copyFailed"));
    }
  }

  return (
    <section className={styles.panel} aria-labelledby="upi-pay-title">
      <h2 id="upi-pay-title" className={styles.title}>
        {t("title", { amount: amount.toFixed(2) })}
      </h2>
      <p className={styles.payee}>{t("payTo", { name: payee.display_name })}</p>

      {/* Kept on a white plate in every theme: a dark-mode-inverted QR will
          not scan. */}
      <div className={styles.qrWrap}>
        <QRCodeSVG value={uri} size={200} level="M" />
      </div>
      <p className={styles.hint}>{ios ? t("scanHintIos") : t("scanHint")}</p>

      <div className={styles.vpaRow}>
        <code className={styles.vpa}>{payee.vpa}</code>
        <button type="button" className="btn" onClick={copyVpa}>
          {copied ? t("copied") : t("copyVpa")}
        </button>
      </div>

      {/* iOS Safari does not reliably fire `upi://`, so the app button is
          demoted there rather than removed — it still works in some apps. */}
      <a className={ios ? "btn" : "btn btn-primary"} href={uri}>
        {t("payWithApp")}
      </a>

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
