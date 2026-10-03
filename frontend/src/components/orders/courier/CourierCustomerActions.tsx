"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useState } from "react";
import { useTranslations } from "next-intl";
import Modal from "@/components/Modal";
import OrderReviewForm from "@/components/orders/OrderReviewForm";
import { useAuth } from "@/lib/AuthContext";
import { errorsKey } from "@/lib/errors";
import { cancelOrder, markCourierReceived, refetchIfStale } from "@/lib/orders";
import type { Order } from "@/types";
import styles from "./courier.module.css";

/** Customer actions on a courier order. Declining a *quote* lives on the
 *  quote card; this bar covers cancel-before-quote, cancel-before-paying,
 *  "I've received it", and rating. */
export default function CourierCustomerActions({
  order,
  onChange,
}: {
  order: Order;
  onChange: (next: Order) => void;
}) {
  const t = useTranslations("Account.orderDetail.courier");
  const tActions = useTranslations("Order.actions");
  const tErr = useTranslations("Errors");
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [reviewOpen, setReviewOpen] = useState(false);

  const claimed = Boolean(order.payment.customer_claimed_at);
  // Spec §9.6: up to `accepted`, until "I've paid". `quoted` → quote card.
  const canCancel = order.status === "pending" || (order.status === "accepted" && !claimed);
  const canReceive = order.status === "dispatched";
  const canRate = order.status === "delivered" && order.review === null;

  async function run(action: () => Promise<Order>) {
    setBusy(true);
    setError(null);
    try {
      onChange(await action());
      setCancelOpen(false);
    } catch (e) {
      const fresh = token ? await refetchIfStale(token, order.id, e) : null;
      if (fresh) onChange(fresh);
      setCancelOpen(false);
      const key = errorsKey(e);
      setError(key ? tErr(key) : t("actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.actions}>
      {canReceive && (
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy}
          onClick={() => {
            if (token && confirm(t("receivedConfirm"))) {
              void run(() => markCourierReceived(token, order.id));
            }
          }}
        >
          {t("received")}
        </button>
      )}
      {canCancel && (
        <button
          type="button"
          className="btn btn-outline"
          disabled={busy}
          onClick={() => setCancelOpen(true)}
        >
          {tActions("cancelOrder")}
        </button>
      )}
      {order.status === "accepted" && claimed && (
        <p className={styles.hint}>{t("cancelAfterClaim", { store: order.store_name })}</p>
      )}
      {canRate && (
        <button type="button" className="btn btn-primary" onClick={() => setReviewOpen(true)}>
          {tActions("rateOrder")}
        </button>
      )}
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      {cancelOpen && (
        <Modal
          title={t("cancelTitle")}
          onClose={() => setCancelOpen(false)}
          footer={
            <>
              <button
                type="button"
                className="btn btn-outline"
                onClick={() => setCancelOpen(false)}
              >
                {t("keepOrder")}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy || !token}
                onClick={() => {
                  if (!token) return;
                  void run(() =>
                    cancelOrder(token, order.id, { reason: reason.trim() || undefined }),
                  );
                }}
              >
                {t("confirmCancel")}
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
        </Modal>
      )}
      {reviewOpen && (
        <Modal title={tActions("rateOrder")} onClose={() => setReviewOpen(false)}>
          <OrderReviewForm
            order={order}
            onSubmitted={(next) => {
              onChange(next);
              setReviewOpen(false);
            }}
          />
        </Modal>
      )}
    </div>
  );
}
