"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useState } from "react";
import { useTranslations } from "next-intl";
import AdminReasonModal from "@/components/admin/AdminReasonModal";
import CourierCancelDialog from "@/components/orders/courier/CourierCancelDialog";
import { adminRefundOrder } from "@/lib/adminActions";
import { useAuth } from "@/lib/AuthContext";
import { errorsKey } from "@/lib/errors";
import { getOrder, refetchIfStale, transitionOrder } from "@/lib/orders";
import { netPayable } from "@/lib/upi";
import type { Order } from "@/types";
import styles from "./courier.module.css";

/** Admin escape hatches on a courier order: cancel (with the payment
 *  question), force-deliver with a reason, and the refund marker. Rewinds
 *  live on the seller hub's orders tab. */
export default function CourierAdminActions({
  order,
  onChange,
}: {
  order: Order;
  onChange: (next: Order) => void;
}) {
  const t = useTranslations("Admin.orderDetail.courier");
  const tErr = useTranslations("Errors");
  const { token } = useAuth();
  const [dialog, setDialog] = useState<"cancel" | "deliver" | "refund" | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (order.delivery_mode !== "courier" || !order.courier) return null;
  const terminal = order.status === "delivered" || order.status === "cancelled";
  const refundable = order.status === "cancelled" && order.courier.refund_due;

  function open(next: "cancel" | "deliver" | "refund") {
    setError(null);
    setDialog(next);
  }

  function close() {
    setError(null);
    setDialog(null);
  }

  /** On failure the reason modal stays open with the message, so the typed
   *  reason isn't lost; the page still catches up on a stale order. */
  async function act(action: (tok: string) => Promise<Order>) {
    if (!token) return;
    setError(null);
    try {
      onChange(await action(token));
      setDialog(null);
    } catch (e) {
      const fresh = await refetchIfStale(token, order.id, e);
      if (fresh) onChange(fresh);
      const key = errorsKey(e);
      setError(key ? tErr(key) : t("actionFailed"));
    }
  }

  return (
    <div className={styles.actions}>
      {order.status === "dispatched" && (
        <button type="button" className="btn btn-primary" onClick={() => open("deliver")}>
          {t("forceDeliver")}
        </button>
      )}
      {refundable && (
        <button type="button" className="btn btn-outline" onClick={() => open("refund")}>
          {t("markRefunded")}
        </button>
      )}
      {!terminal && (
        <button type="button" className="btn btn-danger" onClick={() => open("cancel")}>
          {t("cancel")}
        </button>
      )}
      {error && dialog === null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      {dialog === "cancel" && (
        <CourierCancelDialog
          order={order}
          role="admin"
          onClose={close}
          onRefresh={onChange}
          onDone={(next) => {
            onChange(next);
            setDialog(null);
          }}
        />
      )}
      {dialog === "deliver" && (
        <AdminReasonModal
          title={t("forceDeliverTitle", { id: order.id })}
          description={t("forceDeliverDesc")}
          confirmLabel={t("forceDeliver")}
          destructive={false}
          onConfirm={(reason) =>
            act((tok) => transitionOrder(tok, order.id, "delivered", { reason }))
          }
          onClose={close}
          error={error}
        />
      )}
      {dialog === "refund" && (
        <AdminReasonModal
          title={t("refundTitle", { id: order.id })}
          description={t("refundDesc", { amount: netPayable(order).toFixed(2) })}
          confirmLabel={t("markRefunded")}
          destructive={false}
          onConfirm={(reason) =>
            act(async (tok) => {
              // The marker returns {status}, not the order — re-read it.
              await adminRefundOrder(order.id, { reason }, tok);
              return getOrder(tok, order.id);
            })
          }
          onClose={close}
          error={error}
        />
      )}
    </div>
  );
}
