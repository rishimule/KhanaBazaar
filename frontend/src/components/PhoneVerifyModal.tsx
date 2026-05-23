"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import { useState } from "react";
import { useTranslations } from "next-intl";
import Modal from "@/components/Modal";
import { post } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import type { CustomerProfile } from "@/types";
import styles from "./PhoneVerifyModal.module.css";

interface Props {
  /** Phone already on the profile. If present, the modal skips the
   *  "enter phone" step and asks the user to confirm + receive a code. */
  currentPhone?: string | null;
  onClose: () => void;
  onVerified: (profile: CustomerProfile) => void;
}

type Step = "confirm" | "edit" | "code";

const PHONE_PREFIX = "+91";

function digitsFromIntl(phone: string): string {
  if (!phone) return "";
  const trimmed = phone.replace(/[\s\-()]/g, "");
  const withoutPrefix = trimmed.startsWith(PHONE_PREFIX)
    ? trimmed.slice(PHONE_PREFIX.length)
    : trimmed.replace(/^\+?91/, "");
  return withoutPrefix.replace(/\D/g, "").slice(0, 10);
}

function intlFromDigits(digits: string): string {
  const cleaned = digits.replace(/\D/g, "").slice(0, 10);
  return cleaned.length > 0 ? `${PHONE_PREFIX}${cleaned}` : PHONE_PREFIX;
}

export default function PhoneVerifyModal({
  currentPhone,
  onClose,
  onVerified,
}: Props) {
  const t = useTranslations("Account.profile.phoneVerify");
  const { token } = useAuth();
  const startStep: Step = currentPhone ? "confirm" : "edit";
  const [step, setStep] = useState<Step>(startStep);
  const [phone, setPhone] = useState(
    currentPhone ? intlFromDigits(digitsFromIntl(currentPhone)) : PHONE_PREFIX,
  );
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const errorKey = (e: unknown): string => {
    const detail = (e as { detail?: { error?: string } }).detail;
    return detail?.error ?? "generic";
  };

  const requestOtp = async () => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await post("/api/v1/customers/me/phone/otp/request", { phone }, token);
      setStep("code");
    } catch (e) {
      setError(t(`error.${errorKey(e)}`));
    } finally {
      setBusy(false);
    }
  };

  const verifyOtp = async () => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const next = await post<CustomerProfile>(
        "/api/v1/customers/me/phone/otp/verify",
        { phone, code },
        token,
      );
      onVerified(next);
      onClose();
    } catch (e) {
      setError(t(`error.${errorKey(e)}`));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title={t("title")} onClose={onClose}>
      {step === "confirm" && (
        <div className={styles.body}>
          <p className={styles.muted}>{t("confirmPrompt")}</p>
          <div className={styles.phoneRow}>
            <span className={styles.phoneValue}>{phone}</span>
            <button
              type="button"
              className={styles.linkBtn}
              onClick={() => setStep("edit")}
              disabled={busy}
            >
              {t("editPhone")}
            </button>
          </div>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={requestOtp}
          >
            {t("sendCode")}
          </button>
          {error && <div className={styles.error}>{error}</div>}
        </div>
      )}
      {step === "edit" && (
        <div className={styles.body}>
          <label className={styles.label} htmlFor="kv-phone">
            {t("phoneLabel")}
          </label>
          <div className={styles.phoneInputWrap}>
            <span className={styles.phonePrefix} aria-hidden="true">
              {PHONE_PREFIX}
            </span>
            <input
              id="kv-phone"
              className={`${styles.input} ${styles.phoneInput}`}
              value={digitsFromIntl(phone)}
              onChange={(e) => setPhone(intlFromDigits(e.target.value))}
              placeholder="9876543210"
              inputMode="numeric"
              pattern="[0-9]*"
              maxLength={10}
              autoComplete="tel-national"
              autoFocus
            />
          </div>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || digitsFromIntl(phone).length !== 10}
            onClick={requestOtp}
          >
            {t("sendCode")}
          </button>
          {error && <div className={styles.error}>{error}</div>}
        </div>
      )}
      {step === "code" && (
        <div className={styles.body}>
          <p className={styles.muted}>{t("sentTo", { phone })}</p>
          <label className={styles.label} htmlFor="kv-code">
            {t("codeLabel")}
          </label>
          <input
            id="kv-code"
            className={styles.input}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            inputMode="numeric"
            maxLength={6}
            autoFocus
          />
          <div className={styles.actionsRow}>
            <button
              type="button"
              className={styles.linkBtn}
              onClick={() => {
                setCode("");
                setStep(currentPhone && phone === currentPhone ? "confirm" : "edit");
              }}
              disabled={busy}
            >
              {t("changePhone")}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || code.length !== 6}
              onClick={verifyOtp}
            >
              {t("verify")}
            </button>
          </div>
          {error && <div className={styles.error}>{error}</div>}
        </div>
      )}
    </Modal>
  );
}
