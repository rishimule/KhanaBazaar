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
  onClose: () => void;
  onVerified: (profile: CustomerProfile) => void;
}

export default function PhoneVerifyModal({ onClose, onVerified }: Props) {
  const t = useTranslations("Account.profile.phoneVerify");
  const { token } = useAuth();
  const [step, setStep] = useState<"request" | "verify">("request");
  const [phone, setPhone] = useState("+91");
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
      setStep("verify");
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
      {step === "request" && (
        <div className={styles.body}>
          <label className={styles.label} htmlFor="kv-phone">{t("phoneLabel")}</label>
          <input
            id="kv-phone"
            className={styles.input}
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="+91XXXXXXXXXX"
            inputMode="tel"
            maxLength={20}
          />
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || phone.length < 8}
            onClick={requestOtp}
          >
            {t("sendCode")}
          </button>
          {error && <div className={styles.error}>{error}</div>}
        </div>
      )}
      {step === "verify" && (
        <div className={styles.body}>
          <p className={styles.muted}>{t("sentTo", { phone })}</p>
          <label className={styles.label} htmlFor="kv-code">{t("codeLabel")}</label>
          <input
            id="kv-code"
            className={styles.input}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            inputMode="numeric"
            maxLength={6}
          />
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || code.length !== 6}
            onClick={verifyOtp}
          >
            {t("verify")}
          </button>
          {error && <div className={styles.error}>{error}</div>}
        </div>
      )}
    </Modal>
  );
}
