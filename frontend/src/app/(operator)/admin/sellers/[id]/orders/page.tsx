"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import AdminReasonModal from "@/components/admin/AdminReasonModal";
import PaymentStatusBadge from "@/components/orders/PaymentStatusBadge";
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

interface PendingAction {
  order: Order;
  kind: ActionKind;
  to?: "pending" | "packed";
}

const REWIND_PATH: Record<Order["status"], "pending" | "packed" | null> = {
  pending: null,
  packed: "pending",
  dispatched: "packed",
  delivered: null,
  cancelled: null,
};

export default function AdminOrdersTab({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
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
      setError("Failed to load orders");
    }
  }, [id, token]);

  useEffect(() => {
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
      setActionError(`Action failed: ${msg}`);
      setPending(null);
    }
  }

  if (error) return <div>{error}</div>;

  const writesBlocked =
    hub !== null && hub.verification_status !== "approved";

  return (
    <div>
      <h2 style={{ marginBottom: "0.75rem" }}>Orders ({orders.length})</h2>
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
          Seller is not active — destructive actions disabled.
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
            <th style={cellHead}>Order</th>
            <th style={cellHead}>Status</th>
            <th style={cellHead}>Payment</th>
            <th style={cellHead}>Customer</th>
            <th style={cellHead}>Total</th>
            <th style={cellHead}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => {
            const terminal = o.status === "delivered" || o.status === "cancelled";
            const rewindTo = REWIND_PATH[o.status];
            const refundable =
              (o.status === "cancelled" || o.status === "delivered") &&
              o.payment.status === "paid";
            return (
              <tr key={o.id}>
                <td style={cell}>
                  <Link href={`/admin/orders/${o.id}`}>#{o.id}</Link>
                </td>
                <td style={cell}>{o.status}</td>
                <td style={cell}>
                  <PaymentStatusBadge status={o.payment.status} />
                </td>
                <td style={cell}>{o.customer_name ?? "—"}</td>
                <td style={cell}>₹{o.total.toFixed(2)}</td>
                <td style={cell}>
                  {!terminal && (
                    <button
                      className="btn btn-danger"
                      disabled={writesBlocked}
                      onClick={() =>
                        setPending({ order: o, kind: "cancel" })
                      }
                      style={{ marginRight: 6 }}
                    >
                      Force cancel
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
                      Rewind → {rewindTo}
                    </button>
                  )}
                  {refundable && (
                    <button
                      className="btn btn-outline"
                      disabled={writesBlocked}
                      onClick={() =>
                        setPending({ order: o, kind: "refund" })
                      }
                    >
                      Refund
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>

      {pending && (
        <AdminReasonModal
          title={modalTitle(pending)}
          description={modalDescription(pending)}
          confirmLabel={
            pending.kind === "cancel"
              ? "Cancel order"
              : pending.kind === "rewind"
                ? "Rewind"
                : "Refund"
          }
          destructive
          onConfirm={performAction}
          onClose={() => setPending(null)}
        />
      )}
    </div>
  );
}

function modalTitle(p: PendingAction): string {
  if (p.kind === "cancel") return `Force-cancel order #${p.order.id}?`;
  if (p.kind === "rewind")
    return `Rewind order #${p.order.id} → ${p.to}?`;
  return `Mark payment refunded on order #${p.order.id}?`;
}

function modalDescription(p: PendingAction): string {
  if (p.kind === "cancel")
    return "Cancellation restocks items. Seller is emailed.";
  if (p.kind === "rewind")
    return `Status moves backward from ${p.order.status} to ${p.to}. Seller is emailed.`;
  return "Payment status flips to refunded (manual ledger marker — MVP has no real refund gateway). Seller is emailed.";
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
