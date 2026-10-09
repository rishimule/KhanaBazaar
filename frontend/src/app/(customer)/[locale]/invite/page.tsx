"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { Suspense, useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";

import IndianPhoneField from "@/components/IndianPhoneField";
import { Link } from "@/i18n/navigation";
import { post } from "@/lib/api";
import { setTokens } from "@/lib/authTokens";
import { apiErrorCode } from "@/lib/errors";
import {
  formatIndianMobile,
  isValidIndianMobile,
  nationalDigits,
  toE164,
} from "@/lib/indianPhone";
import { usePhoneOtpEnabled } from "@/lib/publicConfig";
import { acceptCustomerReferral, getInvite, type ReferralInviteDetail } from "@/lib/referrals";
import {
  requestSignupPhoneOtp,
  retryAfterSeconds,
  verifySignupPhoneOtp,
  type SignupPhoneCache,
} from "@/lib/signupPhone";
import { useResendCountdown } from "@/lib/useResendCountdown";
import styles from "./page.module.css";

/** Which call failed: code errors from `verify` are about the phone code,
 * everywhere else about the email code typed on step 2. */
type Stage = "request" | "verify" | "accept";

/** Codes meaning this invite can no longer be used at all. */
const DEAD_INVITE_CODES = new Set([
  "already_active",
  "not_approved",
  "expired",
  "invite_token_expired",
  "invalid_invite_token",
  "not_found",
  "not_a_customer_invite",
]);

const MAX_SEEDED_COUNTDOWN = 120;

export default function InviteAcceptPage() {
  return (
    <Suspense fallback={<div className={styles.wrap} />}>
      <InviteAcceptInner />
    </Suspense>
  );
}

function InviteAcceptInner() {
  const t = useTranslations("Invite");
  const tS = useTranslations("Signup");
  const params = useParams();
  const searchParams = useSearchParams();
  const locale = (params?.locale as string) || "en";
  const token = searchParams.get("token") || "";

  const [detail, setDetail] = useState<ReferralInviteDetail | null>(null);
  const [invalid, setInvalid] = useState(false);
  const [loading, setLoading] = useState(true);
  // 3 = the phone code, shown only when the server answers otp_required: true.
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [emailInput, setEmailInput] = useState("");
  const [code, setCode] = useState("");
  const [fullName, setFullName] = useState("");
  const [phoneDigits, setPhoneDigits] = useState("");
  const [phoneCode, setPhoneCode] = useState("");
  const [signupPhone, setSignupPhone] = useState<SignupPhoneCache>(null);
  const [codeSentFor, setCodeSentFor] = useState<{ email: string; phone: string } | null>(null);
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [emailTaken, setEmailTaken] = useState(false);
  const emailResend = useResendCountdown();
  const phoneResend = useResendCountdown();
  // Labels only — each request's `otp_required` decides whether step 3 shows.
  const phoneOtpEnabled = usePhoneOtpEnabled();
  const phoneInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!token) {
      setInvalid(true);
      setLoading(false);
      return;
    }
    getInvite(token)
      .then((d) => {
        if (d.expired || d.status !== "approved") {
          setInvalid(true);
          return;
        }
        setDetail(d);
        setFullName(d.invitee_name);
        if (d.invitee_email) setEmailInput(d.invitee_email);
        // The referrer's number is only a suggestion; the invitee may change it.
        if (d.invitee_phone) setPhoneDigits(nationalDigits(d.invitee_phone));
      })
      .catch(() => setInvalid(true))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    if (step === 2 && phoneError) phoneInputRef.current?.focus();
  }, [step, phoneError]);

  const effectiveEmail = detail?.invitee_email || emailInput.trim();
  const normalizedEmail = effectiveEmail.toLowerCase();
  const emailLocked = Boolean(detail?.invitee_email);
  const phone = toE164(phoneDigits);
  const phoneValid = isValidIndianMobile(phoneDigits);
  const cachedToken =
    signupPhone && signupPhone.email === normalizedEmail && signupPhone.phone === phone
      ? signupPhone.token
      : null;
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

  const seedableWait = (err: unknown): number | undefined => {
    const seconds = retryAfterSeconds(err);
    return seconds && seconds <= MAX_SEEDED_COUNTDOWN ? seconds : undefined;
  };

  const codeMessage = (errorCode: string | null): string =>
    errorCode === "invalid_code"
      ? t("invalidCode")
      : errorCode === "code_expired_or_used"
        ? t("codeExpired")
        : t("tooManyAttempts");

  /** Spec §5.4, invite flavour (the email code sits on step 2). */
  const handleError = (err: unknown, stage: Stage) => {
    const errorCode = apiErrorCode(err);
    if (errorCode && DEAD_INVITE_CODES.has(errorCode)) {
      setInvalid(true);
      return;
    }
    switch (errorCode) {
      case "invalid_phone":
      case "phone_already_in_use":
        setSignupPhone(null);
        setStep(2);
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
        if (stage !== "verify") {
          // The email code on step 2 is wrong or no longer live.
          setStep(2);
          setCode("");
        }
        setError(codeMessage(errorCode));
        return;
      case "email_already_registered":
      case "already_registered":
        setSignupPhone(null);
        setStep(2);
        setEmailTaken(true);
        setError(tS("errEmailRegistered"));
        return;
      case "phone_required":
      case "invalid_phone_token":
      case "phone_token_expired":
        setSignupPhone(null);
        setStep(2);
        setPhoneError(tS("errConfirmAgain"));
        return;
      case "policy_acceptance_required":
        setStep(2);
        setError(t("policyRequired"));
        return;
      default:
        setError(stage === "request" ? tS("errSendFailed") : t("genericError"));
    }
  };

  const sendCode = async () => {
    if (!effectiveEmail) {
      setError(t("emailRequired"));
      return;
    }
    if (busy || emailResend.active) return;
    setBusy(true);
    setError(null);
    try {
      await post("/api/v1/auth/otp/request", { email: effectiveEmail });
      setCode("");
      setStep(2);
      emailResend.start();
    } catch (err) {
      if (apiErrorCode(err) === "rate_limited") {
        emailResend.start(seedableWait(err));
        setError(rateLimitMessage(err));
      } else {
        setError(t("genericError"));
      }
    } finally {
      setBusy(false);
    }
  };

  /** Create the account; on success the page navigates away, so `busy`
   * deliberately stays on. */
  const accept = async (phoneToken: string) => {
    const res = await acceptCustomerReferral({
      token,
      code: code.trim(),
      email: emailLocked ? undefined : effectiveEmail,
      full_name: fullName.trim() || undefined,
      accept_policies: agree,
      phone_token: phoneToken,
    });
    setTokens(res.access_token, res.refresh_token, res.expires_in);
    window.location.assign(`/${locale}/account`);
  };

  const activate = async () => {
    if (busy) return;
    setError(null);
    setPhoneError(null);
    setEmailTaken(false);
    if (!phoneValid) {
      setPhoneError(tS("errInvalidPhone"));
      return;
    }
    setBusy(true);
    let stage: Stage = "request";
    try {
      if (cachedToken) {
        stage = "accept";
        await accept(cachedToken);
        return;
      }
      if (codeSentFor && codeSentFor.email === normalizedEmail && codeSentFor.phone === phone) {
        setPhoneCode("");
        setStep(3);
        setBusy(false);
        return;
      }
      const res = await requestSignupPhoneOtp({
        email: effectiveEmail,
        email_code: code.trim(),
        phone,
      });
      if (!res.otp_required) {
        if (!res.phone_token) throw new Error("phone_token missing");
        setSignupPhone({ email: normalizedEmail, phone, token: res.phone_token });
        stage = "accept";
        await accept(res.phone_token);
        return;
      }
      setCodeSentFor({ email: normalizedEmail, phone });
      setPhoneCode("");
      setStep(3);
      phoneResend.start();
      setBusy(false);
    } catch (err) {
      handleError(err, stage);
      setBusy(false);
    }
  };

  const verifyPhone = async () => {
    if (busy) return;
    setError(null);
    setBusy(true);
    let stage: Stage = "verify";
    try {
      let phoneToken = cachedToken;
      if (!phoneToken) {
        const res = await verifySignupPhoneOtp({
          email: effectiveEmail,
          phone,
          code: phoneCode,
        });
        phoneToken = res.phone_token;
        setSignupPhone({ email: normalizedEmail, phone, token: phoneToken });
        setCodeSentFor(null);
      }
      stage = "accept";
      await accept(phoneToken);
    } catch (err) {
      handleError(err, stage);
      setBusy(false);
    }
  };

  const resendPhoneCode = async () => {
    if (busy || phoneResend.active) return;
    setError(null);
    setBusy(true);
    let stage: Stage = "request";
    try {
      const res = await requestSignupPhoneOtp({
        email: effectiveEmail,
        email_code: code.trim(),
        phone,
      });
      if (!res.otp_required) {
        // Phone OTP was switched off meanwhile: the number is accepted now.
        if (!res.phone_token) throw new Error("phone_token missing");
        setSignupPhone({ email: normalizedEmail, phone, token: res.phone_token });
        stage = "accept";
        await accept(res.phone_token);
        return;
      }
      setCodeSentFor({ email: normalizedEmail, phone });
      setPhoneCode("");
      phoneResend.start();
      setBusy(false);
    } catch (err) {
      if (apiErrorCode(err) === "rate_limited") phoneResend.start(seedableWait(err));
      handleError(err, stage);
      setBusy(false);
    }
  };

  if (loading) {
    return <div className={styles.wrap}><p className={styles.muted}>{t("loading")}</p></div>;
  }

  if (invalid) {
    return (
      <div className={styles.wrap}>
        <div className={styles.card}>
          <div className={styles.icon}>🎁</div>
          <h1 className={styles.title}>{t("invalidTitle")}</h1>
          <p className={styles.body}>{t("invalidBody")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.icon}>🎁</div>
        <h1 className={styles.title}>{t("greeting")}</h1>
        <p className={styles.body}>{t("intro", { name: detail?.invitee_name ?? "" })}</p>

        {step === 1 && (
          <>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="inv-email">{t("emailLabel")}</label>
              <input
                id="inv-email"
                type="email"
                className={emailLocked ? styles.inputLocked : styles.input}
                value={emailInput}
                onChange={(e) => setEmailInput(e.target.value)}
                readOnly={emailLocked}
                placeholder={t("emailPlaceholder")}
              />
            </div>
            <button className="btn btn-primary" type="button" onClick={sendCode} disabled={busy}>
              {busy ? t("sending") : t("sendCode")}
            </button>
          </>
        )}

        {step === 2 && (
          <>
            <p className={styles.sentNote}>{t("codeSent", { email: effectiveEmail })}</p>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="inv-code">{t("codeLabel")}</label>
              <input
                id="inv-code"
                className={styles.input}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                inputMode="numeric"
                maxLength={8}
                placeholder="••••••"
              />
            </div>
            <div className={styles.linkRow}>
              {emailResend.active ? (
                <span className={styles.muted}>
                  {t("resendEmailIn", { seconds: emailResend.secondsLeft })}
                </span>
              ) : (
                <button type="button" className={styles.linkBtn} onClick={sendCode} disabled={busy}>
                  {t("resendEmailCode")}
                </button>
              )}
            </div>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="inv-name">{t("nameLabel")}</label>
              <input
                id="inv-name"
                className={styles.input}
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                maxLength={120}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="inv-phone">{tS("label")}</label>
              <IndianPhoneField
                id="inv-phone"
                inputRef={phoneInputRef}
                value={phoneDigits}
                onChange={(digits) => {
                  setPhoneDigits(digits);
                  setPhoneError(null);
                }}
                invalid={Boolean(shownPhoneError)}
                describedBy="inv-phone-hint"
              />
              {shownPhoneError ? (
                <span id="inv-phone-hint" className={styles.fieldError} role="alert">
                  {shownPhoneError}
                </span>
              ) : (
                <span id="inv-phone-hint" className={styles.fieldHint}>
                  {phoneHint}
                </span>
              )}
            </div>
            <label className={styles.checkboxRow}>
              <input
                type="checkbox"
                checked={agree}
                onChange={(e) => setAgree(e.target.checked)}
              />
              <span>{t("agree")}</span>
            </label>
            <button
              className="btn btn-primary"
              type="button"
              onClick={activate}
              disabled={busy || !code.trim() || phoneDigits.length !== 10 || !agree}
            >
              {busy ? t("activating") : t("activate")}
            </button>
          </>
        )}

        {step === 3 && (
          <>
            <p className={styles.sentNote}>
              {tS("codeSent", { phone: formatIndianMobile(phone) })}
            </p>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="inv-phone-code">{tS("codeLabel")}</label>
              <input
                id="inv-phone-code"
                className={styles.input}
                value={phoneCode}
                onChange={(e) => setPhoneCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="••••••"
                autoFocus
              />
            </div>
            <button
              className="btn btn-primary"
              type="button"
              onClick={verifyPhone}
              disabled={busy || (phoneCode.length !== 6 && !cachedToken)}
            >
              {busy ? t("activating") : t("verifyAndActivate")}
            </button>
            <div className={styles.linkRow}>
              {phoneResend.active ? (
                <span className={styles.muted}>
                  {tS("resendIn", { seconds: phoneResend.secondsLeft })}
                </span>
              ) : (
                <button
                  type="button"
                  className={styles.linkBtn}
                  onClick={resendPhoneCode}
                  disabled={busy}
                >
                  {tS("resendCode")}
                </button>
              )}
              <button
                type="button"
                className={styles.linkBtn}
                onClick={() => {
                  setStep(2);
                  setPhoneCode("");
                  setError(null);
                }}
                disabled={busy}
              >
                {tS("changeNumber")}
              </button>
            </div>
          </>
        )}
        {error && (
          <div className={styles.errorText} role="alert">
            {error}
            {emailTaken && (
              <>
                {" "}
                <Link href="/login" className={styles.linkBtn}>
                  {t("signIn")}
                </Link>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
