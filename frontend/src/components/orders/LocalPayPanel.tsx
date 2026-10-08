"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { get } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { errorsKey } from "@/lib/errors";
import { claimLocalPayment, refetchIfStale } from "@/lib/orders";
import { netPayable } from "@/lib/upi";
import BankTransferBlock from "@/components/orders/BankTransferBlock";
import UpiQrBlock from "@/components/orders/UpiQrBlock";
import type { Order, OrderPayee, Store } from "@/types";
import styles from "./LocalPayPanel.module.css";

interface Props {
  order: Order;
  onChange: (next: Order) => void;
}

/**
 * Pay panel for local (door / pickup) orders paid by UPI or bank transfer.
 * Self-gating: renders nothing unless the order is local, paid by one of
 * those methods, still pending, not cancelled, with something left to pay —
 * so the order-confirmed and order-detail pages mount it unconditionally.
 *
 * The payee comes from the order (`order.payee`, spec 2026-10-07 §7): the
 * details saved when it was placed, or the store's current ones after the
 * seller switched the method off and on. A null method means the store has
 * stopped taking it. The UPI QR is generated from the VPA — never the seller's
 * uploaded image, whose payee we cannot read.
 */
export default function LocalPayPanel({ order, onChange }: Props) {
  const tUpi = useTranslations("UpiPay");
  const tBank = useTranslations("BankPay");
  const tErr = useTranslations("Errors");
  const { token } = useAuth();
  const method = order.payment.method;
  // The NET figure: `order.total` and `payment.amount` are gross, so billing
  // either would ask a customer holding store credit to overpay.
  const amount = netPayable(order);
  const visible =
    order.delivery_mode !== "courier" &&
    (method === "upi" || method === "net_banking") &&
    order.payment.status === "pending" &&
    order.status !== "cancelled" &&
    amount > 0;
  // An API from before payees were saved per order omits `payee`: fall back
  // to the store's live UPI payee, as this panel used to.
  const legacy = order.payee === undefined;
  const [legacyPayee, setLegacyPayee] = useState<OrderPayee | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!visible || !legacy || method !== "upi") return;
    let cancelled = false;
    get<Store>(`/api/v1/stores/${order.store_id}`)
      .then((s) => {
        if (!cancelled) setLegacyPayee({ upi: s.upi_payee ?? null, bank_transfer: null });
      })
      .catch(() => {
        if (!cancelled) setLegacyPayee({ upi: null, bank_transfer: null });
      });
    return () => {
      cancelled = true;
    };
  }, [visible, legacy, method, order.store_id]);

  if (!visible) return null;
  const payee = legacy ? legacyPayee : order.payee;
  if (!payee) return null;

  const claimed = order.payment.customer_claimed_at;
  const upi = method === "upi" ? payee.upi : null;
  const bank = method === "net_banking" ? payee.bank_transfer : null;
  const stopped = method === "upi" ? !upi : !bank;

  async function claim() {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      onChange(await claimLocalPayment(token, order.id));
    } catch (e) {
      const fresh = await refetchIfStale(token, order.id, e);
      if (fresh) onChange(fresh);
      const key = errorsKey(e);
      setError(key ? tErr(key) : tUpi("claimFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.panel} aria-labelledby="local-pay-title">
      <h2 id="local-pay-title" className={styles.title}>
        {method === "upi"
          ? tUpi("title", { amount: amount.toFixed(2) })
          : tBank("title", { amount: amount.toFixed(2) })}
      </h2>
      {upi && <p className={styles.payee}>{tUpi("payTo", { name: upi.display_name })}</p>}

      {upi && (
        <UpiQrBlock
          vpa={upi.vpa}
          payeeName={upi.display_name}
          amount={amount}
          orderId={order.id}
          onError={setError}
        />
      )}
      {bank && (
        <BankTransferBlock bank={bank} amount={amount} orderId={order.id} onError={setError} />
      )}
      {stopped && (
        <p className={styles.error} role="alert">
          {method === "upi" ? tUpi("stopped") : tBank("stopped")}
          {/* They may have paid before the store switched it off. */}
          {!claimed && ` ${tBank("alreadyPaidHint")}`}
        </p>
      )}

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {claimed ? (
        <p className={styles.claimed} role="status">
          {tUpi("claimedAt", { when: new Date(claimed).toLocaleString("en-IN") })}
        </p>
      ) : (
        <button type="button" className="btn btn-primary" disabled={busy} onClick={claim}>
          {tUpi("ivePaid")}
        </button>
      )}
      <p className={styles.disclaimer}>
        {method === "upi" ? tUpi("disclaimer") : tBank("disclaimer")}
      </p>
    </section>
  );
}
