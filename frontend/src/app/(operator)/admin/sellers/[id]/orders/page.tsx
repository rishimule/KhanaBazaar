"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AdminReasonModal from "@/components/admin/AdminReasonModal";
import CourierCancelDialog from "@/components/orders/courier/CourierCancelDialog";
import OrderStatusBadge from "@/components/orders/OrderStatusBadge";
import PaymentStatusBadge from "@/components/orders/PaymentStatusBadge";
import OrderTotal from "@/components/orders/OrderTotal";
import { useAuth } from "@/lib/AuthContext";
import { post } from "@/lib/api";
import {
  adminRefundOrder,
  adminRewindOrder,
  fetchSellerHub,
  fetchSellerOrders,
} from "@/lib/adminActions";
import type { Order, SellerHubSummary } from "@/types";

type ActionKind = "cancel" | "rewind" | "refund";

type RewindTarget = "pending" | "packed" | "paid" | "accepted";

interface PendingAction {
  order: Order;
  kind: ActionKind;
  to?: RewindTarget;
}

/** One step back, never before the customer's acceptance on a courier order
 *  (spec §9.7). Mirrors the backend's REWIND tables. */
function rewindTarget(order: Order): RewindTarget | null {
  if (order.delivery_mode === "courier") {
    if (order.status === "paid") return "accepted";
    if (order.status === "packed") return "paid";
    if (order.status === "dispatched") return "packed";
    return null;
  }
  if (order.status === "packed") return "pending";
  if (order.status === "dispatched") return "packed";
  return null;
}

export default function AdminOrdersTab({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const t = useTranslations("Admin.sellerHub");
  const { token } = useAuth();
  const [orders, setOrders] = useState<Order[]>([]);
  const [hub, setHub] = useState<SellerHubSummary | null>(null);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const [h, resp] = await Promise.all([
        fetchSellerHub(Number(id), token),
        fetchSellerOrders(Number(id), token),
      ]);
      setHub(h);
      setOrders(resp.orders);
    } catch {
      setError(t("orders.loadError"));
    }
  }, [id, token, t]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial load sets state inside async callbacks
    load();
  }, [load]);

  async function performAction(reason: string) {
    if (!pending || !token) return;
    const o = pending.order;
    setActionError(null);
    try {
      if (pending.kind === "cancel") {
        await post(`/api/v1/orders/${o.id}/cancel`, { reason }, token);
      } else if (pending.kind === "rewind" && pending.to) {
        await adminRewindOrder(o.id, { to_status: pending.to, reason }, token);
      } else if (pending.kind === "refund") {
        await adminRefundOrder(o.id, { reason }, token);
      }
      setPending(null);
      await load();
    } catch (e) {
      const msg = (e as Error).message ?? "unknown_error";
      setActionError(t("orders.actionFailed", { msg }));
      setPending(null);
    }
  }

  if (error) return <div>{error}</div>;

  const writesBlocked =
    hub !== null && hub.verification_status !== "approved";

  return (
    <div>
      <h2 style={{ marginBottom: "0.75rem" }}>{t("orders.heading", { n: orders.length })}</h2>
      {writesBlocked && (
        <div
          style={{
            padding: "0.6rem 0.9rem",
            background: "rgba(245, 158, 11, 0.14)",
            border: "1px solid var(--color-warning)",
            borderRadius: 6,
            marginBottom: "0.75rem",
            color: "var(--color-neutral-900)",
          }}
        >
          {t("orders.writesBlocked")}
        </div>
      )}
      {actionError && (
        <div
          role="alert"
          style={{
            padding: "0.6rem 0.9rem",
            background: "rgba(216, 60, 48, 0.12)",
            border: "1px solid var(--color-error)",
            borderRadius: 6,
            marginBottom: "0.75rem",
            color: "var(--color-error)",
          }}
        >
          {actionError}
        </div>
      )}
      <div style={{ overflowX: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "0.92rem",
        }}
      >
        <thead>
          <tr style={{ background: "var(--color-neutral-50)" }}>
            <th style={cellHead}>{t("orders.col.order")}</th>
            <th style={cellHead}>{t("orders.col.status")}</th>
            <th style={cellHead}>{t("orders.col.payment")}</th>
            <th style={cellHead}>{t("orders.col.customer")}</th>
            <th style={cellHead}>{t("orders.col.total")}</th>
            <th style={cellHead}>{t("orders.col.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => {
            const terminal = o.status === "delivered" || o.status === "cancelled";
            const rewindTo = rewindTarget(o);
            // A cancelled courier order owes a refund only with money paid
            // (`refund_due`: a ₹0 store-credit order owes nothing).
            const refundable =
              o.payment.status === "paid" &&
              (o.status === "delivered" ||
                (o.status === "cancelled" &&
                  (o.delivery_mode !== "courier" || Boolean(o.courier?.refund_due))));
            // Courier: the admin must still be able to cancel and record the
            // refund after the seller lost approval (spec §9.9); the backend
            // allows exactly these two. Rewinds stay blocked.
            const courierEscape = o.delivery_mode === "courier";
            return (
              <tr key={o.id}>
                <td style={cell}>
                  <Link href={`/admin/orders/${o.id}`}>#{o.id}</Link>
                </td>
                <td style={cell}><OrderStatusBadge status={o.status} deliveryMode={o.delivery_mode} /></td>
                <td style={cell}>
                  <PaymentStatusBadge status={o.payment.status} refundDue={o.courier?.refund_due} />
                </td>
                <td style={cell}>{o.customer_name ?? "—"}</td>
                <td style={cell}>
                  <OrderTotal order={o} />
                </td>
                <td style={cell}>
                  {!terminal && (
                    <button
                      className="btn btn-danger"
                      disabled={writesBlocked && !courierEscape}
                      onClick={() =>
                        setPending({ order: o, kind: "cancel" })
                      }
                      style={{ marginRight: 6 }}
                    >
                      {t("orders.forceCancel")}
                    </button>
                  )}
                  {rewindTo && (
                    <button
                      className="btn btn-outline"
                      disabled={writesBlocked}
                      onClick={() =>
                        setPending({ order: o, kind: "rewind", to: rewindTo })
                      }
                      style={{ marginRight: 6 }}
                    >
                      {t("orders.rewindTo", { to: rewindTo })}
                    </button>
                  )}
                  {refundable && (
                    <button
                      className="btn btn-outline"
                      disabled={writesBlocked && !courierEscape}
                      onClick={() =>
                        setPending({ order: o, kind: "refund" })
                      }
                    >
                      {t("orders.refund")}
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>

      {/* The plain reason modal can't ask whether a claimed payment arrived,
          so a courier force-cancel would 422 on payment_received_required. */}
      {pending && pending.kind === "cancel" && pending.order.delivery_mode === "courier" ? (
        <CourierCancelDialog
          order={pending.order}
          role="admin"
          onClose={() => setPending(null)}
          onRefresh={(next) => {
            // Keep the open dialog on the fresh order (e.g. the customer just
            // said they paid, so it must now ask whether the money arrived).
            setPending((p) => (p ? { ...p, order: next } : p));
            void load();
          }}
          onDone={() => {
            setPending(null);
            void load();
          }}
        />
      ) : (
        pending && (
          <AdminReasonModal
            title={modalTitle(pending, t)}
            description={modalDescription(pending, t)}
            confirmLabel={
              pending.kind === "cancel"
                ? t("orders.confirm.cancel")
                : pending.kind === "rewind"
                  ? t("orders.confirm.rewind")
                  : t("orders.confirm.refund")
            }
            destructive
            onConfirm={performAction}
            onClose={() => setPending(null)}
          />
        )
      )}
    </div>
  );
}

type Translator = ReturnType<typeof useTranslations>;

function modalTitle(p: PendingAction, t: Translator): string {
  if (p.kind === "cancel") return t("orders.modal.cancelTitle", { id: p.order.id });
  if (p.kind === "rewind")
    return t("orders.modal.rewindTitle", { id: p.order.id, to: p.to ?? "" });
  return t("orders.modal.refundTitle", { id: p.order.id });
}

function modalDescription(p: PendingAction, t: Translator): string {
  // Courier cancels never get here: they open CourierCancelDialog, which
  // states its own consequences (no restock once shipped, refund due).
  if (p.kind === "cancel")
    return t("orders.modal.cancelDesc");
  if (p.kind === "rewind") {
    const base = t("orders.modal.rewindDesc", { from: p.order.status, to: p.to ?? "" });
    if (p.order.delivery_mode !== "courier") return base;
    // What a courier rewind also undoes (services/orders.rewind_order).
    const extra = [
      p.to === "accepted" ? t("orders.modal.rewindCourierPayment") : null,
      p.order.status === "dispatched" ? t("orders.modal.rewindCourierTracking") : null,
    ].filter(Boolean);
    return [base, ...extra].join(" ");
  }
  return t("orders.modal.refundDesc");
}

const cellHead: React.CSSProperties = {
  textAlign: "left",
  padding: "0.5rem 0.75rem",
  borderBottom: "1px solid var(--color-neutral-200)",
  fontWeight: 500,
};
const cell: React.CSSProperties = {
  padding: "0.45rem 0.75rem",
  borderBottom: "1px solid var(--color-neutral-100)",
};
