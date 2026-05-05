"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { cancelOrder, transitionOrder } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import type { Order, OrderStatus, UserRole } from "@/types";
import styles from "./OrderActionButtons.module.css";

const NEXT_TRANSITION: Partial<Record<OrderStatus, "packed" | "dispatched" | "delivered">> = {
  pending: "packed",
  packed: "dispatched",
  dispatched: "delivered",
};

const NEXT_LABEL_KEYS: Record<NonNullable<typeof NEXT_TRANSITION[OrderStatus]>, string> = {
  packed: "markPacked",
  dispatched: "markDispatched",
  delivered: "markDelivered",
};

interface Props {
  order: Order;
  role: UserRole;
  onChange: (next: Order) => void;
}

export default function OrderActionButtons({ order, role, onChange }: Props) {
  const t = useTranslations("Order.actions");
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canTransition = role === "seller" && NEXT_TRANSITION[order.status] !== undefined;
  const canCancelCustomer = role === "customer" && order.status === "pending";
  const canCancelStaff =
    role !== "customer" && order.status !== "delivered" && order.status !== "cancelled";

  const handleTransition = async () => {
    if (!token) return;
    const target = NEXT_TRANSITION[order.status]!;
    if (target === "delivered" && !confirm(t("confirmCashCollected"))) return;
    setBusy(true);
    setError(null);
    try {
      const next = await transitionOrder(token, order.id, target);
      onChange(next);
    } catch (e) {
      setError((e as { detail?: string })?.detail ?? t("errUpdate"));
    } finally {
      setBusy(false);
    }
  };

  const handleCancel = async () => {
    if (!token) return;
    if (!confirm(t("confirmCancel"))) return;
    setBusy(true);
    setError(null);
    try {
      const next = await cancelOrder(token, order.id);
      onChange(next);
    } catch (e) {
      setError((e as { detail?: string })?.detail ?? t("errCancel"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={styles.actions}>
      {canTransition && (
        <button onClick={handleTransition} disabled={busy} className={styles.primary}>
          {t(NEXT_LABEL_KEYS[NEXT_TRANSITION[order.status]!])}
        </button>
      )}
      {(canCancelCustomer || canCancelStaff) && (
        <button onClick={handleCancel} disabled={busy} className={styles.danger}>
          {t("cancelOrder")}
        </button>
      )}
      {error && <span className={styles.error}>{error}</span>}
    </div>
  );
}
