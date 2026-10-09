"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import { apiErrorCode, apiErrorKey } from "@/lib/errors";
import { useResendCountdown } from "@/lib/useResendCountdown";
import { usePhoneOtpEnabled } from "@/lib/publicConfig";
import { COMPANY_NAME } from "@/lib/brand";
import { formatIndianMobile, isValidIndianMobile, toE164 } from "@/lib/indianPhone";
import {
  requestSignupPhoneOtp,
  retryAfterSeconds,
  verifySignupPhoneOtp,
  type SignupPhoneCache,
} from "@/lib/signupPhone";
import IndianPhoneField from "@/components/IndianPhoneField";
import { User } from "@/types";
import styles from "./page.module.css";

/** `profile` is the new-account step (name + phone + consent); `phoneCode`
 * appears only when the server answers `otp_required: true`. */
type Step = "email" | "code" | "profile" | "phoneCode";

/** Which signup call failed — the same error code means different things:
 * code errors from `verify` are about the phone code, everywhere else about
 * the email code the call re-checked. */
type SignupStage = "request" | "verify" | "create";

const RESEND_COOLDOWN_SECONDS = 60;
/** Longest `retry_after` that seeds a countdown; past it the copy says minutes. */
const MAX_SEEDED_COUNTDOWN = 120;

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
  const tS = useTranslations("Signup");
  const tErr = useTranslations("Errors");
  const router = useRouter();
  const params = useSearchParams();
  const nextParam = params.get("next");
  const { requestOtp, verifyOtp, dbUser } = useAuth();
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [fullName, setFullName] = useState("");
  const [phoneDigits, setPhoneDigits] = useState("");
  const [phoneCode, setPhoneCode] = useState("");
  const [signupPhone, setSignupPhone] = useState<SignupPhoneCache>(null);
  // `email|phone` pairs a phone code went to in this visit: "Change number"
  // and back reuses that code instead of tripping the 60 s cooldown.
  const [codesSent, setCodesSent] = useState<ReadonlySet<string>>(() => new Set());
  const [error, setError] = useState<string | null>(null);
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const [consentRequired, setConsentRequired] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [remember, setRemember] = useState(false);
  const { secondsLeft: resendIn, start: startResend } = useResendCountdown(RESEND_COOLDOWN_SECONDS);
  const phoneResend = useResendCountdown(RESEND_COOLDOWN_SECONDS);
  // Labels only — each request's `otp_required` decides whether a code step shows.
  const phoneOtpEnabled = usePhoneOtpEnabled();
  const phoneInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!dbUser) return;
    router.push(resolveTarget(dbUser, nextParam));
  }, [dbUser, router, nextParam]);

  useEffect(() => {
    get<{ required: boolean }>("/api/v1/policies/status")
      .then((s) => setConsentRequired(s.required))
      .catch(() => setConsentRequired(false));
  }, []);

  // A phone problem sends the customer back to the profile step: put the
  // cursor where the fix goes (the name field would otherwise autofocus).
  useEffect(() => {
    if (step === "profile" && phoneError) phoneInputRef.current?.focus();
  }, [step, phoneError]);

  if (dbUser) {
    return null;
  }

  const normalizedEmail = email.trim().toLowerCase();
  const phone = toE164(phoneDigits);
  const cachedToken =
    signupPhone && signupPhone.email === normalizedEmail && signupPhone.phone === phone
      ? signupPhone.token
      : null;
  const pairKey = `${normalizedEmail}|${phone}`;
  const willSendCode = phoneOtpEnabled && !cachedToken;
  const phoneValid = isValidIndianMobile(phoneDigits);
  const shownPhoneError =
    phoneError ?? (phoneDigits.length > 10 ? tS("errInvalidPhone") : null);
  const phoneHint =
    !phoneOtpEnabled && phoneValid
      ? tS("confirmNumber", { phone: formatIndianMobile(phone) })
      : phoneOtpEnabled
        ? tS("hintOtp")
        : tS("hint");

  const rateLimitMessage = (err: unknown): string => {
    const seconds = retryAfterSeconds(err);
    if (!seconds) return tS("errRateLimitedLater");
    if (seconds > MAX_SEEDED_COUNTDOWN) {
      return tS("errRateLimitedMinutes", { minutes: Math.ceil(seconds / 60) });
    }
    return tS("errRateLimited", { seconds });
  };

  /** A cooldown `retry_after` short enough to count down on the button. */
  const seedableWait = (err: unknown): number | undefined => {
    const seconds = retryAfterSeconds(err);
    return seconds && seconds <= MAX_SEEDED_COUNTDOWN ? seconds : undefined;
  };

  /** Copy for a failed email-code request or check: known codes first; the
   * shared `Errors` copy only for network, server and validation failures;
   * never a raw `HTTP 400`. */
  const emailStepMessage = (err: unknown, fallback: string): string => {
    switch (apiErrorCode(err)) {
      case "invalid_code":
        return t("errInvalidCode");
      case "code_expired_or_used":
        return t("errCodeExpired");
      case "too_many_attempts":
        return t("errTooManyAttempts");
      case "account_suspended":
        return t("errAccountSuspended");
      case "account_deleted":
        return t("errAccountDeleted");
      case "rate_limited":
        return rateLimitMessage(err);
      default: {
        const key = apiErrorKey(err);
        if (key === "Errors.network" || key === "Errors.serverError" || key === "Errors.validation") {
          return tErr(key.replace(/^Errors\./, ""));
        }
        return fallback;
      }
    }
  };

  /** Spec §5.4: route a failed phone request/verify or account creation. */
  const handleSignupError = (err: unknown, stage: SignupStage) => {
    const errorCode = apiErrorCode(err);
    switch (errorCode) {
      case "invalid_phone":
      case "phone_already_in_use":
        setSignupPhone(null);
        setStep("profile");
        setPhoneError(
          errorCode === "invalid_phone" ? tS("errInvalidPhone") : tS("errPhoneInUse"),
        );
        return;
      case "rate_limited":
        setError(rateLimitMessage(err));
        return;
      case "invalid_code":
      case "code_expired_or_used":
      case "too_many_attempts":
        if (stage === "verify") {
          setError(emailStepMessage(err, t("errVerify")));
          return;
        }
        // The email code the call re-checked is no longer live: get a new
        // one. Name, number and any cached token survive the detour.
        setCode("");
        setStep("code");
        setError(t("errEmailCodeStale"));
        return;
      case "email_already_registered":
        setSignupPhone(null);
        setCodesSent(new Set());
        setCode("");
        setStep("email");
        setError(tS("errEmailRegistered"));
        return;
      case "phone_required":
      case "invalid_phone_token":
      case "phone_token_expired":
        // No automatic retry: one explicit tap re-runs the phone step.
        setSignupPhone(null);
        setStep("profile");
        setPhoneError(tS("errConfirmAgain"));
        return;
      case "policy_acceptance_required":
        // The policies fetch may have failed and hidden the checkbox.
        setConsentRequired(true);
        setStep("profile");
        setError(t("errPolicyRequired"));
        return;
      default: {
        const key = apiErrorKey(err);
        if (key === "Errors.network") {
          setError(tErr("network"));
          return;
        }
        setError(
          stage === "create"
            ? t("errCreateAccount")
            : stage === "verify"
              ? t("errVerify")
              : tS("errSendFailed"),
        );
      }
    }
  };

  const finishSignup = async (phoneToken: string) => {
    const result = await verifyOtp(email, code, fullName, agreed, remember, phoneToken);
    router.push(resolveTarget(result.user, nextParam));
  };

  const handleRequestOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await requestOtp(email);
      setStep("code");
      startResend();
    } catch (err) {
      setError(emailStepMessage(err, t("errSendCode")));
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
      const wait = apiErrorCode(err) === "rate_limited" ? seedableWait(err) : undefined;
      if (wait) startResend(wait);
      setError(emailStepMessage(err, t("errSendCode")));
    } finally {
      setResending(false);
    }
  };

  const handleVerifyCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await verifyOtp(email, code, undefined, undefined, remember);
      if (result.needsName) {
        setStep("profile");
      } else {
        router.push(resolveTarget(result.user, nextParam));
      }
    } catch (err) {
      setError(emailStepMessage(err, t("errVerify")));
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmitProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting) return;
    setError(null);
    setPhoneError(null);
    if (!phoneValid) {
      setPhoneError(tS("errInvalidPhone"));
      return;
    }
    setSubmitting(true);
    let stage: SignupStage = "request";
    try {
      if (cachedToken) {
        stage = "create";
        await finishSignup(cachedToken);
        return;
      }
      if (codesSent.has(pairKey)) {
        // The code sent before "Change number" is still the one to type.
        setPhoneCode("");
        setStep("phoneCode");
        return;
      }
      const res = await requestSignupPhoneOtp({ email, email_code: code, phone });
      if (!res.otp_required) {
        if (!res.phone_token) throw new Error("phone_token missing");
        setSignupPhone({ email: normalizedEmail, phone, token: res.phone_token });
        stage = "create";
        await finishSignup(res.phone_token);
        return;
      }
      setCodesSent((prev) => new Set(prev).add(pairKey));
      setPhoneCode("");
      setStep("phoneCode");
      phoneResend.start();
    } catch (err) {
      handleSignupError(err, stage);
    } finally {
      setSubmitting(false);
    }
  };

  const handleVerifyPhoneCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting) return;
    setError(null);
    setSubmitting(true);
    let stage: SignupStage = "verify";
    try {
      // A token from an earlier verify (account creation then failed) is
      // reused: the code it consumed can't be checked twice.
      let token = cachedToken;
      if (!token) {
        const res = await verifySignupPhoneOtp({ email, phone, code: phoneCode });
        token = res.phone_token;
        setSignupPhone({ email: normalizedEmail, phone, token });
        setCodesSent((prev) => {
          const next = new Set(prev);
          next.delete(pairKey);
          return next;
        });
      }
      stage = "create";
      await finishSignup(token);
    } catch (err) {
      handleSignupError(err, stage);
    } finally {
      setSubmitting(false);
    }
  };

  const handleResendPhoneCode = async () => {
    if (phoneResend.active || resending || submitting) return;
    setError(null);
    setResending(true);
    let stage: SignupStage = "request";
    try {
      const res = await requestSignupPhoneOtp({ email, email_code: code, phone });
      if (!res.otp_required) {
        // Phone OTP was switched off meanwhile: the number is accepted now.
        if (!res.phone_token) throw new Error("phone_token missing");
        setSignupPhone({ email: normalizedEmail, phone, token: res.phone_token });
        stage = "create";
        await finishSignup(res.phone_token);
        return;
      }
      setCodesSent((prev) => new Set(prev).add(pairKey));
      setPhoneCode("");
      phoneResend.start();
    } catch (err) {
      const wait = apiErrorCode(err) === "rate_limited" ? seedableWait(err) : undefined;
      if (wait) phoneResend.start(wait);
      handleSignupError(err, stage);
    } finally {
      setResending(false);
    }
  };

  const backToEmail = () => {
    setStep("email");
    setCode("");
    setSignupPhone(null);
    setCodesSent(new Set());
    setError(null);
    setPhoneError(null);
  };

  const subtitle =
    step === "email"
      ? t("subtitleEmail")
      : step === "code"
        ? t("subtitleCode", { email })
        : step === "profile"
          ? t("subtitleProfile")
          : t("subtitlePhoneCode", { phone: formatIndianMobile(phone) });

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
            <label className={styles.consentRow}>
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
              />
              <span>{t("keepSignedIn")}</span>
            </label>
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
            <button type="button" className={styles.testBtn} onClick={backToEmail}>
              {t("useDifferentEmail")}
            </button>
          </form>
        )}

        {step === "profile" && (
          <form className={styles.form} onSubmit={handleSubmitProfile}>
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
            <div className={styles.inputGroup}>
              <label className={styles.label} htmlFor="login-phone">
                {tS("label")}
              </label>
              <IndianPhoneField
                id="login-phone"
                inputRef={phoneInputRef}
                value={phoneDigits}
                onChange={(digits) => {
                  setPhoneDigits(digits);
                  setPhoneError(null);
                }}
                invalid={Boolean(shownPhoneError)}
                describedBy="login-phone-hint"
              />
              {shownPhoneError ? (
                <span id="login-phone-hint" className={styles.fieldError} role="alert">
                  {shownPhoneError}
                </span>
              ) : (
                <span id="login-phone-hint" className={styles.fieldHint}>
                  {phoneHint}
                </span>
              )}
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
              disabled={
                submitting ||
                !fullName.trim() ||
                phoneDigits.length !== 10 ||
                (consentRequired && !agreed)
              }
            >
              {submitting
                ? willSendCode
                  ? t("sending")
                  : t("creatingAccount")
                : willSendCode
                  ? t("continue")
                  : t("createAccount")}
            </button>
            <button type="button" className={styles.testBtn} onClick={backToEmail}>
              {t("useDifferentEmail")}
            </button>
          </form>
        )}

        {step === "phoneCode" && (
          <form className={styles.form} onSubmit={handleVerifyPhoneCode}>
            {error && <div className={styles.error} role="alert">{error}</div>}
            <div className={styles.inputGroup}>
              <label className={styles.label} htmlFor="login-phone-code">
                {tS("codeLabel")}
              </label>
              <input
                id="login-phone-code"
                className={styles.input}
                type="text"
                inputMode="numeric"
                placeholder="123456"
                value={phoneCode}
                onChange={(e) => setPhoneCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                required
                autoComplete="one-time-code"
                autoFocus
              />
            </div>
            <button
              type="submit"
              className={styles.submitBtn}
              disabled={submitting || (phoneCode.length !== 6 && !cachedToken)}
            >
              {submitting ? t("verifying") : t("verifyAndCreate")}
            </button>
            <div className={styles.resendRow}>
              {phoneResend.active ? (
                <span className={styles.resendHint}>
                  {tS("resendIn", { seconds: phoneResend.secondsLeft })}
                </span>
              ) : (
                <button
                  type="button"
                  className={styles.resendBtn}
                  onClick={handleResendPhoneCode}
                  disabled={resending || submitting}
                >
                  {resending ? t("sending") : tS("resendCode")}
                </button>
              )}
            </div>
            <button
              type="button"
              className={styles.testBtn}
              onClick={() => {
                setStep("profile");
                setPhoneCode("");
                setError(null);
              }}
            >
              {tS("changeNumber")}
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
