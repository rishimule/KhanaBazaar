"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useState } from "react";
import { useTranslations } from "next-intl";
import Modal from "@/components/Modal";
import CourierCancelDialog from "@/components/orders/courier/CourierCancelDialog";
import { useAuth } from "@/lib/AuthContext";
import { latestQuote } from "@/lib/courier";
import { errorsKey } from "@/lib/errors";
import {
  confirmCourierPayment,
  markRefundSent,
  refetchIfStale,
  rejectCourierPayment,
  sendCourierQuote,
  transitionOrder,
  updateCourierTracking,
  type TrackingInput,
} from "@/lib/orders";
import { netPayable } from "@/lib/upi";
import type { Order } from "@/types";
import styles from "./courier.module.css";

/** Mirrors COURIER_MAX_QUOTE_VERSIONS (A1 Task 2). The server stays the
 *  authority (`too_many_quote_versions`); this only hides a dead button. */
const MAX_QUOTE_VERSIONS = 5;

type Dialog = "quote" | "notReceived" | "ship" | "tracking" | "refund" | "cancel" | null;

/** Mirrors A1 `validate_tracking_url`: https, a host, no embedded credentials. */
function isSafeTrackingUrl(value: string): boolean {
  if (value.length > 500) return false;
  try {
    const u = new URL(value);
    return u.protocol === "https:" && Boolean(u.hostname) && !u.username && !u.password;
  } catch {
    return false;
  }
}

/** The seller's next step on a courier order — quote, confirm payment, pack,
 *  ship with tracking, deliver (no OTP), and record a refund — with a hint
 *  saying what is happening right now. */
export default function CourierSellerActions({
  order,
  onChange,
}: {
  order: Order;
  onChange: (next: Order) => void;
}) {
  const t = useTranslations("Seller.orderDetail.courier");
  const tc = useTranslations("Order.courier");
  const tErr = useTranslations("Errors");
  const { token } = useAuth();
  const [dialog, setDialog] = useState<Dialog>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fee, setFee] = useState("");
  const [etaMin, setEtaMin] = useState("");
  const [etaMax, setEtaMax] = useState("");
  const [carrier, setCarrier] = useState("");
  const [note, setNote] = useState("");
  const [trackCarrier, setTrackCarrier] = useState("");
  const [trackNumber, setTrackNumber] = useState("");
  const [trackUrl, setTrackUrl] = useState("");
  const [rejectNote, setRejectNote] = useState("");
  const [refundRef, setRefundRef] = useState("");

  const c = order.courier;
  if (order.delivery_mode !== "courier" || !c) return null;
  // Re-bound so the nested closures below see a non-null CourierInfo.
  const courier = c;
  const latest = latestQuote(order);
  const amount = netPayable(order).toFixed(2);
  const claimedAt = order.payment.customer_claimed_at;
  const methodLabel = order.payment.method === "net_banking" ? tc("methodBank") : tc("methodUpi");

  async function run(action: (tok: string) => Promise<Order>) {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      onChange(await action(token));
      setDialog(null);
    } catch (e) {
      // e.g. the customer cancelled while the seller was quoting: catch the
      // page up and keep the message (in the open modal, or under the bar).
      const fresh = await refetchIfStale(token, order.id, e);
      if (fresh) onChange(fresh);
      const key = errorsKey(e);
      setError(key ? tErr(key) : t("actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  function openQuote() {
    setFee(latest ? String(latest.courier_fee) : "");
    setEtaMin(latest ? String(latest.eta_min_days) : "");
    setEtaMax(latest ? String(latest.eta_max_days) : "");
    setCarrier(latest?.carrier_name ?? "");
    setNote("");
    setError(null);
    setDialog("quote");
  }

  function openTracking(kind: "ship" | "tracking") {
    setTrackCarrier(courier.carrier_name ?? latest?.carrier_name ?? "");
    setTrackNumber(courier.tracking_number ?? "");
    setTrackUrl(courier.tracking_url ?? "");
    setError(null);
    setDialog(kind);
  }

  const feeNum = Number(fee);
  const minNum = Number(etaMin);
  const maxNum = Number(etaMax);
  // Mirrors CourierQuoteRequest: fee 0..1,00,000, days 1..60, min <= max.
  const quoteValid =
    fee.trim() !== "" &&
    Number.isFinite(feeNum) &&
    feeNum >= 0 &&
    feeNum <= 100000 &&
    Number.isInteger(minNum) &&
    Number.isInteger(maxNum) &&
    minNum >= 1 &&
    maxNum <= 60 &&
    minNum <= maxNum;
  const urlValid = trackUrl.trim() === "" || isSafeTrackingUrl(trackUrl.trim());

  let hint: string | null = null;
  if (order.status === "pending") hint = t("hintPending");
  else if (order.status === "quoted") hint = t("hintQuoted", { version: latest?.version ?? 1 });
  else if (order.status === "accepted")
    hint = claimedAt
      ? t("hintClaimed", {
          method: methodLabel,
          when: new Date(claimedAt).toLocaleString("en-IN"),
        })
      : courier.payment_claim_rejected_at
        ? t("hintRejected")
        : t("hintAwaitingPayment", { amount });
  else if (order.status === "paid") hint = t("hintPaid");
  else if (order.status === "packed") hint = t("hintPacked");
  else if (order.status === "dispatched") hint = t("hintDispatched");
  else if (order.status === "cancelled" && courier.refund_due) hint = t("hintRefund", { amount });

  const canQuote = order.status === "pending" || order.status === "quoted";
  const quoteLimitReached =
    order.status === "quoted" && courier.quotes.length >= MAX_QUOTE_VERSIONS;
  const canCancel = !["dispatched", "delivered", "cancelled"].includes(order.status);

  const trackingFields = (
    <>
      <label className={styles.field}>
        <span>{t("trackCarrier")}</span>
        <input
          maxLength={80}
          value={trackCarrier}
          onChange={(e) => setTrackCarrier(e.target.value)}
        />
      </label>
      <label className={styles.field}>
        <span>{t("trackNumber")}</span>
        <input
          maxLength={60}
          value={trackNumber}
          onChange={(e) => setTrackNumber(e.target.value)}
        />
      </label>
      <label className={styles.field}>
        <span>{t("trackUrl")}</span>
        <input
          type="url"
          inputMode="url"
          maxLength={500}
          placeholder="https://"
          value={trackUrl}
          aria-invalid={!urlValid || undefined}
          onChange={(e) => setTrackUrl(e.target.value)}
        />
      </label>
      {!urlValid && <p className={styles.error}>{t("trackUrlInvalid")}</p>}
      <p className={styles.hint}>{t("trackHint")}</p>
    </>
  );

  return (
    <div className={styles.fieldset}>
      {hint && (
        <p className={styles.body} role="status">
          {hint}
        </p>
      )}
      <div className={styles.actions}>
        {canQuote && !quoteLimitReached && (
          <button type="button" className="btn btn-primary" disabled={busy} onClick={openQuote}>
            {order.status === "pending" ? t("sendQuote") : t("reviseQuote")}
          </button>
        )}
        {quoteLimitReached && (
          <p className={styles.hint}>{t("quoteLimit", { max: MAX_QUOTE_VERSIONS })}</p>
        )}
        {order.status === "accepted" && (
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => {
              if (confirm(t("confirmPaymentPrompt", { amount }))) {
                void run((tok) => confirmCourierPayment(tok, order.id));
              }
            }}
          >
            {t("confirmPayment")}
          </button>
        )}
        {order.status === "accepted" && claimedAt && (
          <button
            type="button"
            className="btn btn-outline"
            disabled={busy}
            onClick={() => {
              setRejectNote("");
              setError(null);
              setDialog("notReceived");
            }}
          >
            {t("notReceived")}
          </button>
        )}
        {order.status === "paid" && (
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => void run((tok) => transitionOrder(tok, order.id, "packed"))}
          >
            {t("markPacked")}
          </button>
        )}
        {order.status === "packed" && (
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => openTracking("ship")}
          >
            {t("markShipped")}
          </button>
        )}
        {order.status === "dispatched" && (
          <>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() => {
                if (confirm(t("deliverPrompt"))) {
                  void run((tok) => transitionOrder(tok, order.id, "delivered"));
                }
              }}
            >
              {t("markDelivered")}
            </button>
            <button
              type="button"
              className="btn btn-outline"
              disabled={busy}
              onClick={() => openTracking("tracking")}
            >
              {t("editTracking")}
            </button>
          </>
        )}
        {order.status === "cancelled" && courier.refund_due && (
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => {
              setRefundRef("");
              setError(null);
              setDialog("refund");
            }}
          >
            {t("refundSent")}
          </button>
        )}
        {canCancel && (
          <button
            type="button"
            className="btn btn-danger"
            disabled={busy}
            onClick={() => setDialog("cancel")}
          >
            {t("cancel")}
          </button>
        )}
      </div>
      {error && dialog === null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {dialog === "quote" && (
        <Modal
          title={t("quoteTitle")}
          onClose={() => setDialog(null)}
          footer={
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || !quoteValid}
              onClick={() =>
                void run((tok) =>
                  sendCourierQuote(tok, order.id, {
                    courierFee: feeNum,
                    etaMinDays: minNum,
                    etaMaxDays: maxNum,
                    carrierName: carrier.trim() || null,
                    note: note.trim() || null,
                  }),
                )
              }
            >
              {t("quoteSubmit")}
            </button>
          }
        >
          <div className={styles.fieldset}>
            <label className={styles.field}>
              <span>{t("quoteFee")}</span>
              {/* The server rounds to paise, so allow them here. */}
              <input
                type="number"
                min={0}
                max={100000}
                step="0.01"
                inputMode="decimal"
                value={fee}
                onChange={(e) => setFee(e.target.value)}
              />
            </label>
            <label className={styles.field}>
              <span>{t("quoteEtaMin")}</span>
              <input
                type="number"
                min={1}
                max={60}
                step={1}
                inputMode="numeric"
                value={etaMin}
                onChange={(e) => setEtaMin(e.target.value)}
              />
            </label>
            <label className={styles.field}>
              <span>{t("quoteEtaMax")}</span>
              <input
                type="number"
                min={1}
                max={60}
                step={1}
                inputMode="numeric"
                value={etaMax}
                onChange={(e) => setEtaMax(e.target.value)}
              />
            </label>
            <label className={styles.field}>
              <span>{t("quoteCarrier")}</span>
              <input maxLength={80} value={carrier} onChange={(e) => setCarrier(e.target.value)} />
            </label>
            <label className={styles.field}>
              <span>{t("quoteNote")}</span>
              <textarea
                rows={2}
                maxLength={300}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </label>
            {quoteValid ? (
              <p className={styles.hint}>
                {t("quotePreview", {
                  total: (order.subtotal + order.tax + feeNum).toFixed(2),
                })}
              </p>
            ) : (
              (fee !== "" || etaMin !== "" || etaMax !== "") && (
                <p className={styles.error}>{t("quoteInvalid")}</p>
              )
            )}
            {error && (
              <p className={styles.error} role="alert">
                {error}
              </p>
            )}
          </div>
        </Modal>
      )}

      {(dialog === "ship" || dialog === "tracking") && (
        <Modal
          title={dialog === "ship" ? t("shipTitle") : t("trackingTitle")}
          onClose={() => setDialog(null)}
          footer={
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || !urlValid}
              onClick={() => {
                if (dialog === "ship") {
                  // Dispatch sends only what was filled in; nothing is cleared.
                  const tracking: TrackingInput = {};
                  if (trackCarrier.trim()) tracking.carrier_name = trackCarrier.trim();
                  if (trackNumber.trim()) tracking.tracking_number = trackNumber.trim();
                  if (trackUrl.trim()) tracking.tracking_url = trackUrl.trim();
                  void run((tok) => transitionOrder(tok, order.id, "dispatched", tracking));
                } else {
                  // Edit sends every field: "" clears it (A1 TrackingInput).
                  void run((tok) =>
                    updateCourierTracking(tok, order.id, {
                      carrier_name: trackCarrier.trim(),
                      tracking_number: trackNumber.trim(),
                      tracking_url: trackUrl.trim(),
                    }),
                  );
                }
              }}
            >
              {dialog === "ship" ? t("shipSubmit") : t("trackingSubmit")}
            </button>
          }
        >
          <div className={styles.fieldset}>
            {trackingFields}
            {error && (
              <p className={styles.error} role="alert">
                {error}
              </p>
            )}
          </div>
        </Modal>
      )}

      {dialog === "notReceived" && (
        <Modal
          title={t("notReceivedTitle")}
          onClose={() => setDialog(null)}
          footer={
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() =>
                void run((tok) =>
                  rejectCourierPayment(tok, order.id, rejectNote.trim() || undefined),
                )
              }
            >
              {t("notReceivedSubmit")}
            </button>
          }
        >
          <div className={styles.fieldset}>
            <p className={styles.hint}>{t("notReceivedHint")}</p>
            <label className={styles.field}>
              <span>{t("notReceivedNote")}</span>
              <textarea
                rows={3}
                maxLength={300}
                value={rejectNote}
                onChange={(e) => setRejectNote(e.target.value)}
              />
            </label>
            {error && (
              <p className={styles.error} role="alert">
                {error}
              </p>
            )}
          </div>
        </Modal>
      )}

      {dialog === "refund" && (
        <Modal
          title={t("refundTitle")}
          onClose={() => setDialog(null)}
          footer={
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() =>
                void run((tok) => markRefundSent(tok, order.id, refundRef.trim() || undefined))
              }
            >
              {t("refundSubmit")}
            </button>
          }
        >
          <div className={styles.fieldset}>
            <p className={styles.hint}>{t("refundHint", { amount })}</p>
            <label className={styles.field}>
              <span>{t("refundRef")}</span>
              <input
                maxLength={60}
                value={refundRef}
                onChange={(e) => setRefundRef(e.target.value)}
              />
            </label>
            {error && (
              <p className={styles.error} role="alert">
                {error}
              </p>
            )}
          </div>
        </Modal>
      )}

      {dialog === "cancel" && (
        <CourierCancelDialog
          order={order}
          role="seller"
          onClose={() => setDialog(null)}
          onRefresh={onChange}
          onDone={(next) => {
            onChange(next);
            setDialog(null);
          }}
        />
      )}
    </div>
  );
}
