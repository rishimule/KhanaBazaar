"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useState } from "react";
import { useTranslations } from "next-intl";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { apiErrorCode } from "@/lib/errors";
import { resendReceiptOtp } from "@/lib/returns";
import type { ReturnRequest } from "@/types";
import styles from "./ReceiptCodePanel.module.css";

interface Props {
  request: ReturnRequest;
  onChange: (next: ReturnRequest) => void;
  namespace?: string;
}

/** `retry_after` off a `resend_cooldown` error, in seconds. */
function retryAfter(err: unknown): number {
  if (err instanceof ApiError && err.detail && typeof err.detail === "object") {
    const value = (err.detail as { retry_after?: unknown }).retry_after;
    if (typeof value === "number") return value;
  }
  return 0;
}

/**
 * The handover code, shown only to the owning customer while the return is
 * active. Modelled on `orders/DeliveryOtpPanel` — the customer reads it out and
 * the store types it, so it renders nothing for sellers (whose payloads never
 * carry the code at all).
 *
 * "Get a new code" is the way out when the seller mistypes the code until it
 * locks: a fresh code also resets the attempt counter.
 */
export default function ReceiptCodePanel({
  request,
  onChange,
  namespace = "Account.returns",
}: Props) {
  const t = useTranslations(namespace);
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  if (request.status !== "active" || !request.receipt_otp) return null;

  const handleResend = async () => {
    if (!token) return;
    setBusy(true);
    setNote(null);
    try {
      onChange(await resendReceiptOtp(token, request.id));
      setNote(t("handoverResendDone"));
    } catch (e) {
      setNote(
        apiErrorCode(e) === "resend_cooldown"
          ? t("handoverResendCooldown", { seconds: retryAfter(e) })
          : t("handoverResendFailed")
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={styles.panel}>
      <h2 className={styles.title}>{t("handoverCodeTitle")}</h2>
      <p className={styles.code}>{request.receipt_otp}</p>
      <p className={styles.hint}>{t("handoverCodeHint")}</p>
      <p className={styles.hint}>{t("handoverLockedHint")}</p>
      <button
        type="button"
        className={styles.resend}
        onClick={handleResend}
        disabled={busy}
      >
        {t("handoverResend")}
      </button>
      {note && <p className={styles.note}>{note}</p>}
    </section>
  );
}
