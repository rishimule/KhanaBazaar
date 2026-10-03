"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import Modal from "@/components/Modal";
import { useAuth } from "@/lib/AuthContext";
import { formatShortDate, latestQuote, previewEtaWindow } from "@/lib/courier";
import { apiErrorCode, errorsKey } from "@/lib/errors";
import { acceptCourierQuote, cancelOrder, refetchIfStale } from "@/lib/orders";
import type { Order } from "@/types";
import styles from "./courier.module.css";

/** The customer's decision point: the latest quote, Accept or Decline. */
export default function CourierQuoteCard({
  order,
  onChange,
}: {
  order: Order;
  onChange: (next: Order) => void;
}) {
  const t = useTranslations("Account.orderDetail.courier");
  const tErr = useTranslations("Errors");
  const locale = useLocale();
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [declineOpen, setDeclineOpen] = useState(false);
  const [reason, setReason] = useState("");

  const quote = latestQuote(order);
  if (order.delivery_mode !== "courier" || order.status !== "quoted" || !quote) return null;
  const preview = previewEtaWindow(quote);
  // What `order.total` becomes on acceptance (the server adds the charge as
  // the delivery fee); store credit then comes off what's left to pay.
  const total = order.subtotal + order.tax + quote.courier_fee;
  const credit = order.store_credit_applied ?? 0;

  async function accept() {
    if (!token || !quote) return;
    setBusy(true);
    setError(null);
    try {
      onChange(await acceptCourierQuote(token, order.id, quote.id));
    } catch (e) {
      // A revision mid-tap, a cancel in another tab: catch the page up first.
      const fresh = await refetchIfStale(token, order.id, e);
      if (fresh) onChange(fresh);
      if (apiErrorCode(e) === "quote_superseded") {
        setError(t("quoteChanged"));
      } else {
        const key = errorsKey(e);
        setError(key ? tErr(key) : t("actionFailed"));
      }
    } finally {
      setBusy(false);
    }
  }

  async function decline() {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      onChange(await cancelOrder(token, order.id, { reason: reason.trim() || undefined }));
      setDeclineOpen(false);
    } catch (e) {
      const fresh = await refetchIfStale(token, order.id, e);
      if (fresh) onChange(fresh);
      setDeclineOpen(false);
      const key = errorsKey(e);
      setError(key ? tErr(key) : t("actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.card} aria-labelledby="courier-quote-title">
      <h2 id="courier-quote-title" className={styles.title}>
        {order.courier?.revised ? t("quoteRevisedTitle") : t("quoteTitle")}
      </h2>
      <dl className={styles.rows}>
        <dt>{t("courierCharge")}</dt>
        <dd>₹{quote.courier_fee.toFixed(2)}</dd>
        <dt>{t("arrives")}</dt>
        <dd>
          <span>{t("arrivesDays", { min: quote.eta_min_days, max: quote.eta_max_days })}</span>
          <span className={styles.sub}>
            {t("arrivesIfToday", {
              from: formatShortDate(preview.from, locale),
              to: formatShortDate(preview.to, locale),
            })}
          </span>
        </dd>
        {quote.carrier_name && (
          <>
            <dt>{t("carrier")}</dt>
            <dd>{quote.carrier_name}</dd>
          </>
        )}
        <dt>{t("newTotal")}</dt>
        <dd className={styles.total}>₹{total.toFixed(2)}</dd>
      </dl>
      {credit > 0 && (
        <p className={styles.sub}>{t("creditCovers", { amount: credit.toFixed(2) })}</p>
      )}
      {quote.note && <p className={styles.note}>“{quote.note}”</p>}
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      <div className={styles.actions}>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={accept}>
          {t("acceptQuote")}
        </button>
        <button
          type="button"
          className="btn btn-outline"
          disabled={busy}
          onClick={() => setDeclineOpen(true)}
        >
          {t("declineQuote")}
        </button>
      </div>
      {declineOpen && (
        <Modal
          title={t("declineTitle")}
          onClose={() => setDeclineOpen(false)}
          footer={
            <>
              <button
                type="button"
                className="btn btn-outline"
                onClick={() => setDeclineOpen(false)}
              >
                {t("keepOrder")}
              </button>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={decline}>
                {t("confirmDecline")}
              </button>
            </>
          }
        >
          <label className={styles.field}>
            <span>{t("declineReason")}</span>
            <textarea
              rows={3}
              maxLength={300}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <p className={styles.sub}>{t("declineHint")}</p>
        </Modal>
      )}
    </section>
  );
}
