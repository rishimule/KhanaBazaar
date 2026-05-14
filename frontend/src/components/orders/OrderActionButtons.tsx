"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useState } from "react";
import { useTranslations } from "next-intl";
import { cancelOrder, transitionOrder } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import Modal from "@/components/Modal";
import OrderReviewForm from "@/components/orders/OrderReviewForm";
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

  const [reviewOpen, setReviewOpen] = useState(false);
  const canTransition = role === "seller" && NEXT_TRANSITION[order.status] !== undefined;
  const canCancelCustomer = role === "customer" && order.status === "pending";
  const canCancelStaff =
    role !== "customer" && order.status !== "delivered" && order.status !== "cancelled";
  const canRate =
    role === "customer" && order.status === "delivered" && order.review === null;

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
      {canRate && (
        <button
          type="button"
          onClick={() => setReviewOpen(true)}
          className={styles.primary}
        >
          {t("rateOrder")}
        </button>
      )}
      {error && <span className={styles.error}>{error}</span>}
      {reviewOpen && (
        <Modal title={t("rateOrder")} onClose={() => setReviewOpen(false)}>
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
