"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import { apiErrorKey } from "@/lib/errors";
import { useResendCountdown } from "@/lib/useResendCountdown";
import { COMPANY_NAME } from "@/lib/brand";
import { User } from "@/types";
import styles from "./page.module.css";

type Step = "email" | "code" | "name";

const RESEND_COOLDOWN_SECONDS = 60;

function getRedirect(user: User): string {
  if (user.role === "admin") return "/admin";
  if (user.role === "seller") return "/seller";
  return "/account";
}

function safeNext(raw: string | null): string | null {
  if (!raw) return null;
  if (!raw.startsWith("/")) return null;
  if (raw.startsWith("//")) return null;
  if (raw.includes("\\")) return null;
  return raw;
}

function resolveTarget(user: User, nextRaw: string | null): string {
  if (user.role !== "customer") return getRedirect(user);
  return safeNext(nextRaw) ?? getRedirect(user);
}

function LoginPageInner() {
  const t = useTranslations("Login");
  const tErr = useTranslations("Errors");
  const router = useRouter();
  const params = useSearchParams();
  const nextParam = params.get("next");
  const { requestOtp, verifyOtp, dbUser } = useAuth();
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const [consentRequired, setConsentRequired] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const { secondsLeft: resendIn, start: startResend } = useResendCountdown(RESEND_COOLDOWN_SECONDS);

  useEffect(() => {
    if (!dbUser) return;
    router.push(resolveTarget(dbUser, nextParam));
  }, [dbUser, router, nextParam]);

  useEffect(() => {
    get<{ required: boolean }>("/api/v1/policies/status")
      .then((s) => setConsentRequired(s.required))
      .catch(() => setConsentRequired(false));
  }, []);

  if (dbUser) {
    return null;
  }

  const handleRequestOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await requestOtp(email);
      setStep("code");
      startResend();
    } catch (err) {
      const key = apiErrorKey(err);
      if (key) {
        setError(tErr(key.replace(/^Errors\./, "")));
      } else {
        setError(err instanceof Error ? err.message : t("errSendCode"));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleResendCode = async () => {
    if (resendIn > 0 || resending) return;
    setError(null);
    setResending(true);
    try {
      await requestOtp(email);
      setCode("");
      startResend();
    } catch (err) {
      const key = apiErrorKey(err);
      if (key) {
        setError(tErr(key.replace(/^Errors\./, "")));
      } else {
        setError(err instanceof Error ? err.message : t("errSendCode"));
      }
    } finally {
      setResending(false);
    }
  };

  const handleVerifyCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await verifyOtp(email, code);
      if (result.needsName) {
        setStep("name");
      } else {
        router.push(resolveTarget(result.user, nextParam));
      }
    } catch (err) {
      const key = apiErrorKey(err);
      if (key) {
        setError(tErr(key.replace(/^Errors\./, "")));
      } else {
        setError(err instanceof Error ? err.message : t("errVerify"));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmitName = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await verifyOtp(email, code, fullName, agreed);
      router.push(resolveTarget(result.user, nextParam));
    } catch (err) {
      const key = apiErrorKey(err);
      if (key) {
        setError(tErr(key.replace(/^Errors\./, "")));
      } else {
        setError(err instanceof Error ? err.message : t("errCreateAccount"));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const subtitle =
    step === "email"
      ? t("subtitleEmail")
      : step === "code"
      ? t("subtitleCode", { email })
      : t("subtitleName");

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <div className={styles.cardLogo}>🛍️</div>
          <h1 className={styles.cardTitle}>
            {t("welcomeTo")}{" "}
            <span className={styles.cardTitleAccent}>{COMPANY_NAME}</span>
          </h1>
          <p className={styles.cardSubtitle}>{subtitle}</p>
        </div>

        {step === "email" && (
          <form className={styles.form} onSubmit={handleRequestOtp}>
            {error && <div className={styles.error} role="alert">{error}</div>}
            <div className={styles.inputGroup}>
              <label className={styles.label} htmlFor="login-email">
                {t("emailLabel")}
              </label>
              <input
                id="login-email"
                className={styles.input}
                type="email"
                placeholder={t("emailPlaceholder")}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </div>
            <button
              type="submit"
              className={styles.submitBtn}
              disabled={submitting}
            >
              {submitting ? t("sending") : t("sendCode")}
            </button>
          </form>
        )}

        {step === "code" && (
          <form className={styles.form} onSubmit={handleVerifyCode}>
            {error && <div className={styles.error} role="alert">{error}</div>}
            <div className={styles.inputGroup}>
              <label className={styles.label} htmlFor="login-code">
                {t("codeLabel")}
              </label>
              <input
                id="login-code"
                className={styles.input}
                type="text"
                inputMode="numeric"
                pattern="\d{6}"
                maxLength={6}
                placeholder="123456"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                required
                autoComplete="one-time-code"
                autoFocus
              />
            </div>
            <button
              type="submit"
              className={styles.submitBtn}
              disabled={submitting}
            >
              {submitting ? t("verifying") : t("verifyCode")}
            </button>
            <div className={styles.resendRow}>
              {resendIn > 0 ? (
                <span className={styles.resendHint}>
                  {t("resendIn", { seconds: resendIn })}
                </span>
              ) : (
                <button
                  type="button"
                  className={styles.resendBtn}
                  onClick={handleResendCode}
                  disabled={resending}
                >
                  {resending ? t("sending") : t("resendCode")}
                </button>
              )}
            </div>
            <button
              type="button"
              className={styles.testBtn}
              onClick={() => {
                setStep("email");
                setCode("");
                setError(null);
              }}
            >
              {t("useDifferentEmail")}
            </button>
          </form>
        )}

        {step === "name" && (
          <form className={styles.form} onSubmit={handleSubmitName}>
            {error && <div className={styles.error} role="alert">{error}</div>}
            <div className={styles.inputGroup}>
              <label className={styles.label} htmlFor="login-name">
                {t("nameLabel")}
              </label>
              <input
                id="login-name"
                className={styles.input}
                type="text"
                placeholder={t("namePlaceholder")}
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                autoComplete="name"
                autoFocus
              />
            </div>
            {consentRequired && (
              <label className={styles.consentRow}>
                <input
                  type="checkbox"
                  checked={agreed}
                  onChange={(e) => setAgreed(e.target.checked)}
                  required
                />
                <span>
                  {t.rich("consent", {
                    terms: (c) => (
                      <a href="/terms" target="_blank" rel="noopener noreferrer">{c}</a>
                    ),
                    privacy: (c) => (
                      <a href="/privacy" target="_blank" rel="noopener noreferrer">{c}</a>
                    ),
                  })}
                </span>
              </label>
            )}
            <button
              type="submit"
              className={styles.submitBtn}
              disabled={submitting || (consentRequired && !agreed)}
            >
              {submitting ? t("creatingAccount") : t("continue")}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div style={{ minHeight: "100vh" }} />}>
      <LoginPageInner />
    </Suspense>
  );
}
