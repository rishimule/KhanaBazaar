"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { use, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import ReturnStatusBadge from "@/components/returns/ReturnStatusBadge";
import { useAuth } from "@/lib/AuthContext";
import { apiErrorCode } from "@/lib/errors";
import {
  acceptReturn,
  getSellerReturn,
  rejectReturn,
  returnErrorKey,
} from "@/lib/returns";
import type { ReturnRequest } from "@/types";
import styles from "./page.module.css";

/** Pulls `remaining` off a receipt_otp_invalid detail so the seller knows how
 *  many tries are left before the code locks. */
function remainingAttempts(err: unknown): number | null {
  const detail = (err as { detail?: unknown })?.detail;
  if (detail && typeof detail === "object") {
    const value = (detail as Record<string, unknown>).remaining;
    if (typeof value === "number") return value;
  }
  return null;
}

export default function SellerReturnDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const returnId = Number(id);
  const t = useTranslations("Seller.returns");
  const { token } = useAuth();

  const [request, setRequest] = useState<ReturnRequest | null>(null);
  const [failed, setFailed] = useState(false);
  const [otp, setOtp] = useState("");
  const [restock, setRestock] = useState(false);
  const [reason, setReason] = useState("");
  const [confirmingReject, setConfirmingReject] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    // Reset on id change: without this, navigating between returns can paint
    // the previous one's data, and a single failure pins the error banner on
    // every return opened afterwards.
    setRequest(null);
    setFailed(false);
    (async () => {
      try {
        const data = await getSellerReturn(token, returnId);
        if (!cancelled) setRequest(data);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, returnId]);

  if (failed) {
    return (
      <p role="alert" className={styles.error}>
        {t("loadFailed")}
      </p>
    );
  }
  if (!request) return <p className={styles.muted}>{t("loading")}</p>;

  const decidable = request.status === "active";

  const doAccept = async () => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      setRequest(await acceptReturn(token, request.id, otp.trim(), restock));
      setOtp("");
    } catch (e) {
      const code = apiErrorCode(e);
      if (code === "receipt_otp_locked") {
        setLocked(true);
        setError(t("errors.receipt_otp_locked"));
      } else if (code === "receipt_otp_invalid") {
        const left = remainingAttempts(e);
        setError(
          left === null
            ? t("errors.receipt_otp_invalid")
            : t("errors.receipt_otp_invalid_remaining", { remaining: left })
        );
      } else {
        setError(t(`errors.${returnErrorKey(code, "operator")}`));
      }
    } finally {
      setBusy(false);
    }
  };

  const doReject = async () => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      setRequest(await rejectReturn(token, request.id, reason.trim()));
      setConfirmingReject(false);
      setReason("");
    } catch (e) {
      setError(t(`errors.${returnErrorKey(apiErrorCode(e), "operator")}`));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h2 className={styles.title}>
          {t("detailTitle", { id: request.id, orderId: request.order_id })}
        </h2>
        <ReturnStatusBadge status={request.status} namespace="Seller.returns" />
      </header>

      <section className={styles.card}>
        <h3 className={styles.heading}>{t("itemsTitle")}</h3>
        <ul className={styles.items}>
          {request.items.map((item) => (
            <li key={item.order_item_id}>
              <span>
                {item.product_name} × {item.quantity}
              </span>
              <span>₹{item.line_total.toFixed(2)}</span>
            </li>
          ))}
        </ul>
        <p className={styles.total}>
          {t("totalLine", { amount: request.total_amount.toFixed(2) })}
        </p>
        <p className={styles.muted}>
          {t("reasonLine", { reason: t(`reason.${request.reason_code}`) })}
          {request.reason_note ? ` — ${request.reason_note}` : ""}
        </p>
        <p className={styles.muted}>
          {t(
            request.settlement_choice === "store_credit"
              ? "settlementCredit"
              : "settlementPayment"
          )}
        </p>
      </section>

      {decidable && (
        <section className={styles.card}>
          <h3 className={styles.heading}>{t("acceptTitle")}</h3>
          <p className={styles.muted}>{t("acceptHint")}</p>
          <input
            className={styles.otpInput}
            inputMode="numeric"
            maxLength={6}
            value={otp}
            disabled={locked}
            aria-label={t("otpLabel")}
            onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
          />
          <label className={styles.checkboxRow}>
            <input
              type="checkbox"
              checked={restock}
              onChange={(e) => setRestock(e.target.checked)}
            />
            <span>{t("restockLabel")}</span>
          </label>
          <p className={styles.hint}>{t("restockHint")}</p>
          <button
            type="button"
            className="btn btn-primary"
            disabled={otp.length !== 6 || busy || locked}
            onClick={doAccept}
          >
            {t("acceptAction")}
          </button>
        </section>
      )}

      {decidable && (
        <section className={styles.card}>
          <h3 className={styles.heading}>{t("rejectTitle")}</h3>
          <p className={styles.muted}>{t("rejectHint")}</p>
          <label className={styles.label} htmlFor="seller-reject-reason">
            {t("rejectReasonPlaceholder")}
          </label>
          <textarea
            id="seller-reject-reason"
            className={styles.textarea}
            value={reason}
            maxLength={500}
            placeholder={t("rejectReasonPlaceholder")}
            onChange={(e) => setReason(e.target.value)}
          />
          {confirmingReject ? (
            <div className={styles.confirmRow}>
              <span className={styles.muted}>{t("rejectConfirm")}</span>
              <button
                type="button"
                className={styles.danger}
                disabled={busy}
                onClick={doReject}
              >
                {t("rejectConfirmYes")}
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => setConfirmingReject(false)}
              >
                {t("cancel")}
              </button>
            </div>
          ) : (
            <button
              type="button"
              className={styles.danger}
              disabled={!reason.trim() || busy}
              onClick={() => setConfirmingReject(true)}
            >
              {t("rejectAction")}
            </button>
          )}
        </section>
      )}

      {request.status === "rejected" && request.rejection_reason && (
        <section className={styles.card}>
          <h3 className={styles.heading}>{t("rejectedTitle")}</h3>
          <p className={styles.muted}>{request.rejection_reason}</p>
        </section>
      )}

      {error && (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      )}
    </div>
  );
}
