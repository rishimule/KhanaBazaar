"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { use, useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import ReceiptCodePanel from "@/components/returns/ReceiptCodePanel";
import ReturnStatusBadge from "@/components/returns/ReturnStatusBadge";
import ReturnTimeline from "@/components/returns/ReturnTimeline";
import { useAuth } from "@/lib/AuthContext";
import { apiErrorCode } from "@/lib/errors";
import {
  confirmPaymentReceived,
  getReturn,
  requestPaymentOtp,
  withdrawReturn,
} from "@/lib/returns";
import type { ReturnRequest } from "@/types";
import styles from "./page.module.css";

export default function ReturnDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const returnId = Number(id);
  const t = useTranslations("Account.returns");
  const { token } = useAuth();

  const [request, setRequest] = useState<ReturnRequest | null>(null);
  const [failed, setFailed] = useState(false);
  const [otp, setOtp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setRequest(await getReturn(token, returnId));
    } catch {
      setFailed(true);
    }
  }, [token, returnId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (failed) {
    return (
      <p role="alert" className={styles.error}>
        {t("loadFailed")}
      </p>
    );
  }
  if (!request) return <p className={styles.muted}>{t("loading")}</p>;

  const canWithdraw =
    request.status === "awaiting_customer_confirmation" ||
    request.status === "active";

  const sendOtp = async () => {
    if (!token) return;
    setNotice(null);
    setError(null);
    try {
      await requestPaymentOtp(token, request.id);
      setNotice(t("paymentOtpSent"));
    } catch (e) {
      setError(t(`errors.${apiErrorCode(e) ?? "unknown"}`));
    }
  };

  const confirmPayment = async () => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      setRequest(await confirmPaymentReceived(token, request.id, otp.trim()));
      setOtp("");
    } catch (e) {
      setError(t(`errors.${apiErrorCode(e) ?? "unknown"}`));
    } finally {
      setBusy(false);
    }
  };

  const doWithdraw = async () => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      setRequest(await withdrawReturn(token, request.id));
    } catch (e) {
      setError(t(`errors.${apiErrorCode(e) ?? "unknown"}`));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>
          {t("rowTitle", { id: request.id, orderId: request.order_id })}
        </h1>
        <ReturnStatusBadge status={request.status} />
      </header>

      <ReturnTimeline request={request} />

      <ReceiptCodePanel request={request} />

      <section className={styles.card}>
        <h2 className={styles.heading}>{t("itemsTitle")}</h2>
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
        <dl className={styles.summary}>
          <div>
            <dt>{t("summaryItems")}</dt>
            <dd>₹{request.items_amount.toFixed(2)}</dd>
          </div>
          {request.delivery_fee_amount > 0 && (
            <div>
              <dt>{t("summaryDeliveryFee")}</dt>
              <dd>₹{request.delivery_fee_amount.toFixed(2)}</dd>
            </div>
          )}
          <div className={styles.total}>
            <dt>{t("summaryTotal")}</dt>
            <dd>₹{request.total_amount.toFixed(2)}</dd>
          </div>
        </dl>
      </section>

      {(request.credit_reversal_amount > 0 ||
        request.store_credit_amount > 0 ||
        request.payment_amount > 0) && (
        <section className={styles.card}>
          <h2 className={styles.heading}>{t("settlementTitle")}</h2>
          <ul className={styles.settlement}>
            {request.credit_reversal_amount > 0 && (
              <li>
                {t("settlementReversal", {
                  amount: request.credit_reversal_amount.toFixed(2),
                })}
              </li>
            )}
            {request.store_credit_amount > 0 && (
              <li>
                {t("settlementStoreCredit", {
                  amount: request.store_credit_amount.toFixed(2),
                })}
              </li>
            )}
            {request.payment_amount > 0 && (
              <li>
                {t("settlementPaymentDue", {
                  amount: request.payment_amount.toFixed(2),
                })}
              </li>
            )}
          </ul>
        </section>
      )}

      {request.status === "rejected" && request.rejection_reason && (
        <section className={styles.card}>
          <h2 className={styles.heading}>{t("rejectedTitle")}</h2>
          <p className={styles.muted}>{request.rejection_reason}</p>
          <p className={styles.muted}>{t("rejectedSettleOffline")}</p>
        </section>
      )}

      {request.status === "awaiting_payment_confirmation" && (
        <section className={styles.card}>
          <h2 className={styles.heading}>{t("confirmPaymentTitle")}</h2>
          <p className={styles.muted}>{t("confirmPaymentHint")}</p>
          <button type="button" className={styles.linkButton} onClick={sendOtp}>
            {t("sendPaymentOtp")}
          </button>
          <input
            className={styles.otpInput}
            inputMode="numeric"
            maxLength={6}
            value={otp}
            aria-label={t("otpLabel")}
            onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
          />
          <button
            type="button"
            className="btn btn-primary"
            disabled={otp.length !== 6 || busy}
            onClick={confirmPayment}
          >
            {t("confirmPaymentAction")}
          </button>
        </section>
      )}

      {canWithdraw && (
        <button
          type="button"
          className={styles.withdraw}
          disabled={busy}
          onClick={doWithdraw}
        >
          {t("withdraw")}
        </button>
      )}

      {notice && <p className={styles.muted}>{notice}</p>}
      {error && (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      )}
    </div>
  );
}
