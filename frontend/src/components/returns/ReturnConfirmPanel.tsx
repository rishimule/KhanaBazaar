"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState, type ReactNode } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { apiErrorCode } from "@/lib/errors";
import {
  confirmReturn,
  getReturnAgreement,
  resendReturnOtp,
  returnErrorKey,
} from "@/lib/returns";
import type { ReturnInitiator, ReturnRequest } from "@/types";
import styles from "./ReturnConfirmPanel.module.css";

interface Props {
  request: ReturnRequest;
  /**
   * `page` — the return page: shows what is being agreed to and asks for
   * consent to the published agreement, because the customer may never have
   * seen it (a seller or admin started the return, or they left the wizard).
   * `wizard` — the wizard's last step: the summary is already on screen and
   * the agreement was accepted one step earlier, so only the code remains.
   */
  variant: "page" | "wizard";
  onConfirmed: (next: ReturnRequest) => void;
  /** Rendered beside the confirm button (the wizard's withdraw). */
  extraActions?: ReactNode;
}

const STARTED_BY: Record<ReturnInitiator, string> = {
  customer: "startedBySelf",
  seller: "startedByStore",
  admin: "startedBySupport",
};

type AgreementState =
  | { status: "loading" }
  | { status: "ok"; body: string }
  | { status: "error" };

/**
 * Confirms a return that is waiting on the customer, with the initiation code
 * we sent them. The single place a pending return is confirmed.
 */
export default function ReturnConfirmPanel({
  request,
  variant,
  onConfirmed,
  extraActions,
}: Props) {
  const t = useTranslations("Account.returns");
  const locale = useLocale();
  const { token } = useAuth();
  const needsAgreement = variant === "page";

  const [agreement, setAgreement] = useState<AgreementState>({
    status: "loading",
  });
  const [accepted, setAccepted] = useState(false);
  const [otp, setOtp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!needsAgreement) return;
    let cancelled = false;
    (async () => {
      try {
        const doc = await getReturnAgreement();
        if (!cancelled) setAgreement({ status: "ok", body: doc.body });
      } catch {
        // Never let a failed fetch read as "there are no terms": without an
        // agreement on screen the customer cannot consent, so confirm stays off.
        if (!cancelled) setAgreement({ status: "error" });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [needsAgreement]);

  const consentGiven =
    !needsAgreement || (agreement.status === "ok" && accepted);
  const canConfirm = otp.length === 6 && consentGiven && !busy;

  const resend = async () => {
    if (!token) return;
    setNotice(null);
    try {
      await resendReturnOtp(token, request.id);
      setNotice(t("otpResent"));
    } catch (e) {
      setNotice(
        apiErrorCode(e) === "resend_cooldown"
          ? t("otpCooldown")
          : t("otpResendFailed")
      );
    }
  };

  const submit = async () => {
    if (!token || !canConfirm) return;
    setBusy(true);
    setError(null);
    try {
      const next = await confirmReturn(token, request.id, otp.trim());
      setOtp("");
      onConfirmed(next);
    } catch (e) {
      setError(t(`errors.${returnErrorKey(apiErrorCode(e), "customer")}`));
    } finally {
      setBusy(false);
    }
  };

  const codeField = `return-otp-${request.id}`;

  return (
    <section
      className={variant === "page" ? styles.panel : styles.bare}
      aria-label={t("confirmTitle")}
    >
      {variant === "page" && (
        <>
          <h2 className={styles.heading}>{t("confirmTitle")}</h2>
          <p className={styles.muted}>{t(STARTED_BY[request.initiated_by])}</p>
          <ul className={styles.facts}>
            <li>
              {t("reasonLine", { reason: t(`reason.${request.reason_code}`) })}
              {request.reason_note ? ` — ${request.reason_note}` : ""}
            </li>
            <li>
              {t(
                request.settlement_choice === "store_credit"
                  ? "choiceCredit"
                  : "choicePayment"
              )}
            </li>
            <li>
              {t("confirmBy", {
                date: new Intl.DateTimeFormat(locale, {
                  dateStyle: "medium",
                  timeStyle: "short",
                }).format(new Date(request.confirm_expires_at)),
              })}
            </li>
          </ul>

          <h3 className={styles.subheading}>{t("agreementTitle")}</h3>
          {agreement.status === "loading" && (
            <p className={styles.muted}>{t("loading")}</p>
          )}
          {agreement.status === "error" && (
            <p role="alert" className={styles.error}>
              {t("agreementLoadFailed")}
            </p>
          )}
          {agreement.status === "ok" && (
            <>
              <div className={styles.agreement}>
                <pre className={styles.agreementBody}>{agreement.body}</pre>
              </div>
              <label className={styles.acceptRow}>
                <input
                  type="checkbox"
                  checked={accepted}
                  onChange={(e) => setAccepted(e.target.checked)}
                />
                <span>{t("acceptAgreement")}</span>
              </label>
            </>
          )}
        </>
      )}

      <label className={styles.label} htmlFor={codeField}>
        {t("otpLabel")}
      </label>
      <input
        id={codeField}
        className={styles.otpInput}
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        value={otp}
        onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
      />
      <button type="button" className={styles.linkButton} onClick={resend}>
        {t("otpResend")}
      </button>
      {notice && <p className={styles.muted}>{notice}</p>}

      <div className={styles.actions}>
        <button
          type="button"
          className="btn btn-primary"
          disabled={!canConfirm}
          onClick={submit}
        >
          {t("confirmReturn")}
        </button>
        {extraActions}
      </div>
      {error && (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      )}
    </section>
  );
}
