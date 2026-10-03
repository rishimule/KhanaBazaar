"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useState } from "react";
import { useTranslations } from "next-intl";
import Modal from "@/components/Modal";
import { useAuth } from "@/lib/AuthContext";
import { errorsKey } from "@/lib/errors";
import { cancelOrder, refetchIfStale } from "@/lib/orders";
import { netPayable } from "@/lib/upi";
import type { Order } from "@/types";
import styles from "./courier.module.css";

/** Seller/admin cancel of a courier order (spec §9.6). A reason of at least
 *  10 characters, plus "Did ₹X reach you?" once the customer has said they
 *  paid and nobody has confirmed it — only the canceller can answer that, and
 *  the answer decides whether a refund is owed. */
export default function CourierCancelDialog({
  order,
  role,
  onClose,
  onDone,
  onRefresh,
}: {
  order: Order;
  role: "seller" | "admin";
  onClose: () => void;
  onDone: (next: Order) => void;
  /** Called with a fresh order when the cancel hit a stale page (403/409). */
  onRefresh?: (next: Order) => void;
}) {
  const t = useTranslations("Order.courierCancel");
  const tErr = useTranslations("Errors");
  const { token } = useAuth();
  const [reason, setReason] = useState("");
  const [received, setReceived] = useState<"yes" | "no" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const payable = netPayable(order);
  const amount = payable.toFixed(2);
  const askReceived =
    order.payment.status === "pending" && Boolean(order.payment.customer_claimed_at);
  const refundOwed = payable > 0 && (order.payment.status === "paid" || received === "yes");
  const reasonOk = reason.trim().length >= 10;
  const canSubmit = Boolean(token) && reasonOk && (!askReceived || received !== null) && !busy;

  async function submit() {
    if (!token || !canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      onDone(
        await cancelOrder(token, order.id, {
          reason: reason.trim(),
          paymentReceived: askReceived ? received === "yes" : undefined,
        }),
      );
    } catch (e) {
      const fresh = await refetchIfStale(token, order.id, e);
      if (fresh) onRefresh?.(fresh);
      const key = errorsKey(e);
      setError(key ? tErr(key) : t("failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={t("title", { id: order.id })}
      onClose={onClose}
      describedById="courier-cancel-consequence"
      footer={
        <>
          <button type="button" className="btn btn-outline" onClick={onClose} disabled={busy}>
            {t("keep")}
          </button>
          <button type="button" className="btn btn-danger" onClick={submit} disabled={!canSubmit}>
            {busy ? "…" : t("confirm")}
          </button>
        </>
      }
    >
      <div id="courier-cancel-consequence" className={styles.fieldset}>
        <p className={styles.warning}>
          {order.status === "dispatched" ? t("consequenceShipped") : t("consequenceRestock")}
        </p>
        {refundOwed && <p className={styles.refund}>{t("consequenceRefund", { amount })}</p>}
        {askReceived && received === "no" && (
          <p className={styles.note}>{t("consequenceMissing")}</p>
        )}
      </div>
      <label className={styles.field}>
        <span>{t("reasonLabel")}</span>
        <textarea
          rows={3}
          maxLength={300}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      {reason.length > 0 && !reasonOk && <p className={styles.hint}>{t("reasonTooShort")}</p>}
      {askReceived && (
        <fieldset className={styles.fieldset}>
          <legend className={styles.legend}>
            {role === "seller"
              ? t("receivedQuestionSeller", { amount })
              : t("receivedQuestionAdmin", { amount })}
          </legend>
          <div className={styles.radioRow}>
            <label>
              <input
                type="radio"
                name="payment-received"
                checked={received === "yes"}
                onChange={() => setReceived("yes")}
              />{" "}
              {t("receivedYes")}
            </label>
            <label>
              <input
                type="radio"
                name="payment-received"
                checked={received === "no"}
                onChange={() => setReceived("no")}
              />{" "}
              {t("receivedNo")}
            </label>
          </div>
        </fieldset>
      )}
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </Modal>
  );
}
