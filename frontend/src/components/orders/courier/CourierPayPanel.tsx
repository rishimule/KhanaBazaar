"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import BankTransferBlock from "@/components/orders/BankTransferBlock";
import UpiQrBlock from "@/components/orders/UpiQrBlock";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { formatDateTime } from "@/lib/courier";
import { errorsKey } from "@/lib/errors";
import { claimCourierPayment, refetchIfStale } from "@/lib/orders";
import { netPayable } from "@/lib/upi";
import type { Order, Store } from "@/types";
import styles from "./courier.module.css";

type Method = "upi" | "net_banking";

/** Pay for an accepted courier order: a tab per live method, then "I've paid"
 *  naming the method used (spec D7). Bills `netPayable(order)` — the gross
 *  total minus store credit, the same figure LocalPayPanel bills. */
export default function CourierPayPanel({
  order,
  onChange,
}: {
  order: Order;
  onChange: (next: Order) => void;
}) {
  const t = useTranslations("Account.orderDetail.courier");
  const tUpi = useTranslations("UpiPay");
  const tErr = useTranslations("Errors");
  const locale = useLocale();
  const { token } = useAuth();
  const courier = order.courier;
  const methods = (courier?.payable_methods ?? []).filter(
    (m): m is Method => m === "upi" || m === "net_banking",
  );
  const visible = order.delivery_mode === "courier" && order.status === "accepted" && !!courier;
  const preferred: Method =
    order.payment.method === "net_banking" && methods.includes("net_banking")
      ? "net_banking"
      : methods[0] ?? "upi";
  const [picked, setPicked] = useState<Method>(preferred);
  // A payee the seller switched off since the page loaded drops out of
  // `payable_methods`; never leave the customer on a tab that can't be paid.
  const tab: Method = methods.includes(picked) ? picked : (methods[0] ?? picked);
  // The payee saved on the order (spec 2026-10-07 §7). An API older than
  // per-order payees omits `payee`: fall back to the store's live UPI payee
  // and the courier block's bank details, as this panel used to.
  const legacy = order.payee === undefined;
  const [legacyUpi, setLegacyUpi] = useState<NonNullable<Store["upi_payee"]> | null>(null);
  const [legacyUpiFailed, setLegacyUpiFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const upiLive = methods.includes("upi");

  useEffect(() => {
    if (!visible || !upiLive || !legacy) return;
    let cancelled = false;
    get<Store>(`/api/v1/stores/${order.store_id}`)
      .then((s) => {
        if (cancelled) return;
        // UPI listed as payable but no payee on the store (switched off since
        // the order loaded): say so instead of "loading" forever.
        if (s.upi_payee) setLegacyUpi(s.upi_payee);
        else setLegacyUpiFailed(true);
      })
      .catch(() => {
        if (!cancelled) setLegacyUpiFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [visible, upiLive, legacy, order.store_id]);

  const payee = legacy ? legacyUpi : (order.payee?.upi ?? null);
  // A per-order payee arrives with the order, so a missing one is final.
  const payeeFailed = legacy ? legacyUpiFailed : payee === null;

  if (!visible || !courier) return null;
  const claimed = order.payment.customer_claimed_at;
  // In the page language (not a fixed en-IN) and the viewer's time zone.
  const claimedLine = claimed
    ? t("claimedAt", {
        when: formatDateTime(claimed, locale),
        store: order.store_name,
      })
    : null;
  if (methods.length === 0) {
    // Once the customer has said they paid, cancelling is no longer theirs to
    // do, so "can't take payments — cancel" would mislead: show the claim.
    return (
      <section className={styles.card}>
        {claimedLine ? (
          <p className={styles.claimed} role="status">
            {claimedLine}
          </p>
        ) : (
          <p className={styles.error} role="alert">
            {t("payeeUnavailable")}
          </p>
        )}
      </section>
    );
  }

  const amount = netPayable(order);

  async function claim() {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      onChange(await claimCourierPayment(token, order.id, tab));
    } catch (e) {
      const fresh = await refetchIfStale(token, order.id, e);
      if (fresh) onChange(fresh);
      const key = errorsKey(e);
      setError(key ? tErr(key) : t("claimFailed"));
    } finally {
      setBusy(false);
    }
  }

  const bank = legacy ? courier.bank_transfer : (order.payee?.bank_transfer ?? null);
  return (
    <section className={`${styles.card} ${styles.center}`} aria-labelledby="courier-pay-title">
      <h2 id="courier-pay-title" className={styles.title} tabIndex={-1}>
        {t("payTitle", { amount: amount.toFixed(2) })}
      </h2>
      {tab === "upi" && payee && (
        <p className={styles.sub}>{tUpi("payTo", { name: payee.display_name })}</p>
      )}
      {courier.payment_claim_rejected_at && (
        <p className={styles.warning} role="status">
          {courier.payment_claim_rejected_note
            ? t("claimRejectedWithNote", { note: courier.payment_claim_rejected_note })
            : t("claimRejected")}
        </p>
      )}
      {/* Toggle buttons, not ARIA tabs: there is no tab panel to control. */}
      {methods.length > 1 && (
        <div className={styles.tabs} role="group" aria-labelledby="courier-pay-title">
          {methods.map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={tab === m}
              className={tab === m ? styles.tabActive : styles.tab}
              onClick={() => setPicked(m)}
            >
              {m === "upi" ? t("tabUpi") : t("tabBank")}
            </button>
          ))}
        </div>
      )}
      {tab === "upi" &&
        (payee ? (
          <UpiQrBlock
            vpa={payee.vpa}
            payeeName={payee.display_name}
            amount={amount}
            orderId={order.id}
            onError={setError}
          />
        ) : payeeFailed ? (
          <p className={styles.error} role="alert">
            {/* Only point at bank transfer when it can actually be used. */}
            {methods.includes("net_banking") ? t("payeeLoadError") : t("payeeLoadErrorRetry")}
          </p>
        ) : (
          <p className={styles.muted}>{t("loadingPayee")}</p>
        ))}
      {tab === "net_banking" &&
        (bank ? (
          <BankTransferBlock bank={bank} amount={amount} orderId={order.id} onError={setError} />
        ) : (
          <p className={styles.error} role="alert">
            {t("payeeUnavailable")}
          </p>
        ))}
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      {claimedLine ? (
        <p className={styles.claimed} role="status">
          {claimedLine}
        </p>
      ) : (
        <button type="button" className="btn btn-primary" disabled={busy} onClick={claim}>
          {tUpi("ivePaid")}
        </button>
      )}
      <p className={styles.disclaimer}>{t("payDisclaimer")}</p>
    </section>
  );
}
