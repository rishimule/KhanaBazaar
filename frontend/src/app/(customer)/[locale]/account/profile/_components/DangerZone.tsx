"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useState } from "react";
import { useTranslations } from "next-intl";
import Modal, { modalStyles } from "@/components/Modal";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { useResendCountdown } from "@/lib/useResendCountdown";
import {
  deactivateAccount,
  deleteAccount,
  requestAccountDeleteOtp,
} from "@/lib/account";
import styles from "./DangerZone.module.css";

type Step = "idle" | "deactivate" | "delete-warning" | "delete-otp";

/** Pull the structured `{error, ...}` payload out of an ApiError, if present.
 *  The API client stores the raw `detail`, which for the lifecycle endpoints is
 *  an object (`open_obligations` / `rate_limited` / `otp_invalid`). */
function detailOf(err: unknown): Record<string, unknown> | null {
  if (err instanceof ApiError && err.detail && typeof err.detail === "object") {
    return err.detail as Record<string, unknown>;
  }
  return null;
}

export default function DangerZone() {
  const t = useTranslations("Account.danger");
  const { token, logout } = useAuth();
  const resend = useResendCountdown();

  const [step, setStep] = useState<Step>("idle");
  const [reason, setReason] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const describeError = (err: unknown): string => {
    const d = detailOf(err);
    const errorCode = typeof d?.error === "string" ? d.error : null;
    if (errorCode === "open_obligations") {
      return t("obligationsBody", {
        orders: Number(d?.open_orders ?? 0),
        credits: Number(d?.credit_accounts ?? 0),
      });
    }
    if (errorCode === "rate_limited") {
      return t("rateLimited", { seconds: Number(d?.retry_after ?? 60) });
    }
    if (errorCode === "otp_invalid") return t("otpInvalid");
    if (err instanceof TypeError) return t("networkError");
    return t("genericError");
  };

  const close = () => {
    if (busy) return;
    setStep("idle");
    setError(null);
    setReason("");
    setCode("");
  };

  const openDeactivate = () => {
    setError(null);
    setReason("");
    setStep("deactivate");
  };

  const openDelete = () => {
    setError(null);
    setCode("");
    setStep("delete-warning");
  };

  const onDeactivate = async () => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await deactivateAccount(token, reason.trim() || null);
      // Tears down the session + clears the token; the account layout effect
      // then redirects to /login. Leave `busy` set so the button stays disabled
      // through the unmount.
      logout();
    } catch (err) {
      setError(describeError(err));
      setBusy(false);
    }
  };

  const onSendDeleteCode = async () => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await requestAccountDeleteOtp(token);
      setCode("");
      setStep("delete-otp");
      resend.start();
    } catch (err) {
      // A cooldown means a code was already sent recently — advance to entry so
      // the customer can use it, and surface the wait. Other errors (e.g. open
      // obligations) keep them on the warning screen.
      if (detailOf(err)?.error === "rate_limited") {
        setCode("");
        setStep("delete-otp");
        resend.start();
      }
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };

  const onResend = async () => {
    if (!token || resend.active) return;
    setBusy(true);
    setError(null);
    try {
      await requestAccountDeleteOtp(token);
      resend.start();
    } catch (err) {
      setError(describeError(err));
      if (detailOf(err)?.error === "rate_limited") resend.start();
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async () => {
    if (!token || code.length !== 6) return;
    setBusy(true);
    setError(null);
    try {
      await deleteAccount(token, code, reason.trim() || null);
      logout();
    } catch (err) {
      setError(describeError(err));
      setBusy(false);
    }
  };

  return (
    <section className={styles.card} aria-labelledby="danger-zone-heading">
      <h2 id="danger-zone-heading" className={styles.heading}>
        {t("title")}
      </h2>

      <div className={styles.rows}>
        <div className={styles.row}>
          <div className={styles.rowText}>
            <h3 className={styles.rowTitle}>{t("deactivateTitle")}</h3>
            <p className={styles.rowSubtitle}>{t("deactivateSubtitle")}</p>
          </div>
          <button
            type="button"
            className={styles.outlineDanger}
            onClick={openDeactivate}
          >
            {t("deactivateButton")}
          </button>
        </div>

        <div className={styles.divider} />

        <div className={styles.row}>
          <div className={styles.rowText}>
            <h3 className={styles.rowTitle}>{t("deleteTitle")}</h3>
            <p className={styles.rowSubtitle}>{t("deleteSubtitle")}</p>
          </div>
          <button
            type="button"
            className={styles.solidDanger}
            onClick={openDelete}
          >
            {t("deleteButton")}
          </button>
        </div>
      </div>

      {step === "deactivate" && (
        <Modal
          title={t("deactivateModalTitle")}
          onClose={close}
          footer={
            <>
              <button
                type="button"
                className={styles.ghostBtn}
                onClick={close}
                disabled={busy}
              >
                {t("cancel")}
              </button>
              <button
                type="button"
                className={styles.solidDanger}
                onClick={onDeactivate}
                disabled={busy}
              >
                {busy ? t("working") : t("deactivateConfirm")}
              </button>
            </>
          }
        >
          <p className={styles.modalBody}>{t("deactivateModalBody")}</p>
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label} htmlFor="deactivate-reason">
              {t("reasonLabel")}
            </label>
            <textarea
              id="deactivate-reason"
              className={modalStyles.textarea}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={t("reasonPlaceholder")}
              maxLength={500}
              rows={3}
            />
          </div>
          {error && (
            <p className={styles.errorText} role="alert">
              {error}
            </p>
          )}
        </Modal>
      )}

      {step === "delete-warning" && (
        <Modal
          title={t("deleteModalTitle")}
          onClose={close}
          footer={
            <>
              <button
                type="button"
                className={styles.ghostBtn}
                onClick={close}
                disabled={busy}
              >
                {t("cancel")}
              </button>
              <button
                type="button"
                className={styles.solidDanger}
                onClick={onSendDeleteCode}
                disabled={busy}
              >
                {busy ? t("working") : t("sendCode")}
              </button>
            </>
          }
        >
          <p className={styles.modalBody}>{t("deleteModalBody")}</p>
          <div className={styles.warningCallout} role="note">
            <span aria-hidden="true">⚠</span> {t("cannotUndo")}
          </div>
          <p className={styles.modalHint}>{t("emailCodeHint")}</p>
          {error && (
            <p className={styles.errorText} role="alert">
              {error}
            </p>
          )}
        </Modal>
      )}

      {step === "delete-otp" && (
        <Modal
          title={t("otpModalTitle")}
          onClose={close}
          footer={
            <>
              <button
                type="button"
                className={styles.ghostBtn}
                onClick={close}
                disabled={busy}
              >
                {t("cancel")}
              </button>
              <button
                type="button"
                className={styles.solidDanger}
                onClick={onDelete}
                disabled={busy || code.length !== 6}
              >
                {busy ? t("working") : t("deleteConfirm")}
              </button>
            </>
          }
        >
          <p className={styles.modalBody}>{t("otpModalBody")}</p>
          <input
            id="delete-otp-code"
            className={styles.codeInput}
            value={code}
            onChange={(e) =>
              setCode(e.target.value.replace(/\D/g, "").slice(0, 6))
            }
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            aria-label={t("otpInputLabel")}
            autoFocus
          />
          <div className={styles.resendRow}>
            {resend.active ? (
              <span className={styles.muted}>
                {t("resendIn", { seconds: resend.secondsLeft })}
              </span>
            ) : (
              <button
                type="button"
                className={styles.linkBtn}
                onClick={onResend}
                disabled={busy}
              >
                {t("resend")}
              </button>
            )}
          </div>
          {error && (
            <p className={styles.errorText} role="alert">
              {error}
            </p>
          )}
        </Modal>
      )}
    </section>
  );
}
