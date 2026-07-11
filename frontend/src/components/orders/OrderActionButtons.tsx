"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useState } from "react";
import { useTranslations } from "next-intl";
import { cancelOrder, transitionOrder } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import { ApiError } from "@/lib/api";
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

function errorDetail(e: unknown): { code?: string; remaining?: number } | null {
  if (e instanceof ApiError && e.detail && typeof e.detail === "object") {
    return e.detail as { code?: string; remaining?: number };
  }
  return null;
}

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

  // Delivery-handover OTP (seller) / force-deliver reason (admin) modals.
  const [otpOpen, setOtpOpen] = useState(false);
  const [otpValue, setOtpValue] = useState("");
  const [otpError, setOtpError] = useState<string | null>(null);
  const [reasonOpen, setReasonOpen] = useState(false);
  const [reasonValue, setReasonValue] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);

  const nextStep = NEXT_TRANSITION[order.status];
  const isDeliverStep = nextStep === "delivered";
  const isPickup = order.delivery_mode === "pickup";
  // Pickup relabels the seller's next-step button: "Ready for pickup" / "Confirm collection".
  const nextLabelKey = !nextStep
    ? ""
    : isPickup && nextStep === "dispatched"
      ? "markReadyForPickup"
      : isPickup && nextStep === "delivered"
        ? "confirmCollection"
        : NEXT_LABEL_KEYS[nextStep];
  const canTransition =
    (role === "seller" && nextStep !== undefined) ||
    (role === "admin" && isDeliverStep);
  const canCancelCustomer = role === "customer" && order.status === "pending";
  const canCancelStaff =
    role !== "customer" && order.status !== "delivered" && order.status !== "cancelled";
  const canRate =
    role === "customer" && order.status === "delivered" && order.review === null;

  const handleTransition = async () => {
    if (!token || !nextStep) return;
    // Delivered requires verification: seller enters the customer's OTP;
    // admin force-delivers with a reason. Both go through a modal.
    if (isDeliverStep) {
      if (role === "admin") {
        setReasonValue("");
        setReasonError(null);
        setReasonOpen(true);
      } else {
        setOtpValue("");
        setOtpError(null);
        setOtpOpen(true);
      }
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const next = await transitionOrder(token, order.id, nextStep);
      onChange(next);
    } catch (e) {
      setError((e as { detail?: string })?.detail ?? t("errUpdate"));
    } finally {
      setBusy(false);
    }
  };

  const submitOtp = async () => {
    if (!token) return;
    setBusy(true);
    setOtpError(null);
    try {
      const next = await transitionOrder(token, order.id, "delivered", {
        otp: otpValue.trim(),
      });
      onChange(next);
      setOtpOpen(false);
    } catch (e) {
      const d = errorDetail(e);
      if (d?.code === "delivery_otp_invalid") {
        setOtpError(t("otpInvalid", { remaining: d.remaining ?? 0 }));
      } else if (d?.code === "delivery_otp_locked") {
        setOtpError(t("otpLocked"));
      } else if (d?.code === "delivery_otp_required") {
        setOtpError(t("otpRequired"));
      } else {
        setOtpError(t("errUpdate"));
      }
    } finally {
      setBusy(false);
    }
  };

  const submitReason = async () => {
    if (!token) return;
    if (reasonValue.trim().length < 10) {
      setReasonError(t("reasonTooShort"));
      return;
    }
    setBusy(true);
    setReasonError(null);
    try {
      const next = await transitionOrder(token, order.id, "delivered", {
        reason: reasonValue.trim(),
      });
      onChange(next);
      setReasonOpen(false);
    } catch (e) {
      const d = errorDetail(e);
      setReasonError(d?.code === "reason_required" ? t("reasonTooShort") : t("errUpdate"));
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
          {role === "admin" && isDeliverStep
            ? t("forceDeliver")
            : t(nextLabelKey)}
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
      {otpOpen && (
        <Modal title={t("otpTitle")} onClose={() => setOtpOpen(false)}>
          <div className={styles.modalBody}>
            <label className={styles.modalLabel} htmlFor="delivery-otp">
              {t("otpLabel")}
            </label>
            <input
              id="delivery-otp"
              className={styles.otpInput}
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              maxLength={6}
              aria-describedby={otpError ? "delivery-otp-error" : undefined}
              value={otpValue}
              onChange={(e) => setOtpValue(e.target.value.replace(/\D/g, ""))}
            />
            {otpError && (
              <span id="delivery-otp-error" className={styles.error}>
                {otpError}
              </span>
            )}
            <button
              type="button"
              onClick={submitOtp}
              disabled={busy || otpValue.trim().length === 0}
              className={styles.primary}
            >
              {t("otpSubmit")}
            </button>
          </div>
        </Modal>
      )}
      {reasonOpen && (
        <Modal title={t("reasonTitle")} onClose={() => setReasonOpen(false)}>
          <div className={styles.modalBody}>
            <label className={styles.modalLabel} htmlFor="force-deliver-reason">
              {t("reasonLabel")}
            </label>
            <textarea
              id="force-deliver-reason"
              className={styles.modalInput}
              rows={3}
              value={reasonValue}
              onChange={(e) => setReasonValue(e.target.value)}
            />
            {reasonError && <span className={styles.error}>{reasonError}</span>}
            <button
              type="button"
              onClick={submitReason}
              disabled={busy || reasonValue.trim().length < 10}
              className={styles.primary}
            >
              {t("reasonSubmit")}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
