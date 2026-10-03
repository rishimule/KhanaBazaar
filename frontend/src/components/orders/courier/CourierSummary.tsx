"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { formatShortDate, latestQuote, straightLineKm, trackingHost } from "@/lib/courier";
import { netPayable } from "@/lib/upi";
import type { Order } from "@/types";
import styles from "./courier.module.css";

/** Recipient, arrival, tracking, cancellation and refund state of a courier
 *  order — the facts every role needs, in one card. Operators also get the
 *  distance and every quote version (spec §13: customers see only the latest). */
export default function CourierSummary({
  order,
  viewer,
}: {
  order: Order;
  viewer: "customer" | "seller" | "admin";
}) {
  const t = useTranslations("Order.courier");
  const locale = useLocale();
  const [copied, setCopied] = useState(false);
  const c = order.courier;
  if (order.delivery_mode !== "courier" || !c) return null;
  const quote = latestQuote(order);
  const host = trackingHost(c.tracking_url);
  // The cash the customer sent. Store credit comes back on its own at cancel
  // (revert_order), and `store_credit_applied` is never cleared, so this is
  // exactly what the seller owes back.
  const amount = netPayable(order).toFixed(2);
  const km = viewer === "customer" ? null : straightLineKm(order);
  const trackingNumber = c.tracking_number;
  // Arrival rows mean nothing on a cancelled order, and while a quote waits
  // the customer's quote card already says how long it takes.
  const showArrival =
    order.status !== "cancelled" && !(viewer === "customer" && order.status === "quoted");
  const claimedAt = order.payment.customer_claimed_at;
  const methodLabel = order.payment.method === "net_banking" ? t("methodBank") : t("methodUpi");

  async function copyTracking() {
    if (!trackingNumber) return;
    try {
      await navigator.clipboard.writeText(trackingNumber);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard blocked: the number is on screen to copy by hand.
    }
  }

  return (
    <section className={styles.card} aria-label={t("summaryLabel")}>
      <dl className={styles.rows}>
        <dt>{t("recipient")}</dt>
        {/* `.rows dd` is a grid, so name and phone stack — no separator. */}
        <dd>
          <span>{c.recipient_name}</span>
          <a href={`tel:${c.recipient_phone}`}>{c.recipient_phone}</a>
        </dd>
        {km !== null && (
          <>
            <dt>{t("distance")}</dt>
            <dd>{t("distanceKm", { km: Math.round(km) })}</dd>
          </>
        )}
        {/* The seller's action bar says this already; admins see it here. */}
        {viewer === "admin" && order.status === "accepted" && claimedAt && (
          <>
            <dt>{t("claimedRow")}</dt>
            <dd>
              {t("claimedValue", {
                method: methodLabel,
                when: new Date(claimedAt).toLocaleString("en-IN"),
              })}
            </dd>
          </>
        )}
        {!showArrival ? null : c.eta_from && c.eta_to ? (
          <>
            <dt>{t("estimatedArrival")}</dt>
            <dd>
              {formatShortDate(c.eta_from, locale)} – {formatShortDate(c.eta_to, locale)}
            </dd>
          </>
        ) : quote ? (
          <>
            <dt>{t("transit")}</dt>
            <dd>{t("transitDays", { min: quote.eta_min_days, max: quote.eta_max_days })}</dd>
          </>
        ) : null}
        {(c.carrier_name || trackingNumber || c.tracking_url) && (
          <>
            <dt>{t("tracking")}</dt>
            <dd>
              {c.carrier_name && <span>{c.carrier_name}</span>}
              {trackingNumber && (
                <span className={styles.actions}>
                  <code>{trackingNumber}</code>
                  <button type="button" className="btn" onClick={copyTracking}>
                    {copied ? t("copied") : t("copy")}
                  </button>
                </span>
              )}
              {c.tracking_url && host && (
                <a href={c.tracking_url} target="_blank" rel="noopener noreferrer nofollow">
                  {t("trackOn", { host })}
                </a>
              )}
            </dd>
          </>
        )}
        {order.status === "delivered" && c.delivered_by && (
          <>
            <dt>{t("deliveredBy")}</dt>
            <dd>{t(`deliveredBy_${c.delivered_by}`)}</dd>
          </>
        )}
      </dl>
      {viewer !== "customer" && c.quotes.length > 0 && (
        <details>
          <summary>{t("quoteHistory", { count: c.quotes.length })}</summary>
          <ol className={styles.points}>
            {c.quotes.map((q) => (
              <li key={q.id}>
                {t("quoteLine", {
                  version: q.version,
                  fee: q.courier_fee.toFixed(2),
                  min: q.eta_min_days,
                  max: q.eta_max_days,
                })}
                {q.carrier_name ? ` · ${q.carrier_name}` : ""}
                {q.id === c.accepted_quote_id ? ` · ${t("quoteAccepted")}` : ""}
              </li>
            ))}
          </ol>
        </details>
      )}
      {order.status === "cancelled" && c.cancel_reason && (
        <p className={styles.note}>{t("cancelReason", { reason: c.cancel_reason })}</p>
      )}
      {c.refund_due && (
        <p className={styles.refund} role="status">
          {viewer === "customer"
            ? t("refundDueCustomer", { amount, store: order.store_name })
            : t("refundDueOperator", { amount })}
        </p>
      )}
      {order.payment.status === "refunded" && order.payment.refunded_at && (
        <p className={styles.note}>
          {t("refunded", {
            amount,
            date: formatShortDate(new Date(order.payment.refunded_at), locale),
          })}
          {order.payment.refund_reference
            ? ` · ${t("refundRef", { ref: order.payment.refund_reference })}`
            : ""}
        </p>
      )}
      {c.payment_reported_missing_at && (
        <p className={styles.warning}>
          {viewer !== "customer"
            ? t("reportedMissingOperator")
            : c.cancelled_by === "admin"
              ? t("reportedMissingCustomerSupport", { store: order.store_name })
              : t("reportedMissingCustomer", { store: order.store_name })}
        </p>
      )}
    </section>
  );
}
