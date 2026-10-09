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
  asciiDigits,
  formatIndianMobile,
  isValidIndianMobile,
  nationalDigits,
  toE164,
} from "@/lib/indianPhone";
import { usePhoneOtpEnabled } from "@/lib/publicConfig";
import { acceptCustomerReferral, getInvite, type ReferralInviteDetail } from "@/lib/referrals";
import {
  codeAlreadySent,
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

type FocusTarget = "phone" | "code";

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
/** See the login page: default OTP lifetime minus a lost response's cooldown. */
const FALLBACK_CODE_LIFETIME_MS = 9 * 60 * 1000;

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
  const tL = useTranslations("Login");
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
  // `email|phone` → when the phone code sent to it expires (see login page).
  const [codesSent, setCodesSent] = useState<ReadonlyMap<string, number>>(
    () => new Map(),
  );
  const [agree, setAgree] = useState(false);
  // Activation (phone request / verify / accept) vs the two resend links, so
  // a resend never relabels the main button "Activating…".
  const [busy, setBusy] = useState(false);
  const [sendingEmail, setSendingEmail] = useState(false);
  const [resendingPhone, setResendingPhone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [emailTaken, setEmailTaken] = useState(false);
  const emailResend = useResendCountdown();
  const phoneResend = useResendCountdown();
  // Labels only — each request's `otp_required` decides whether step 3 shows.
  const phoneOtpEnabled = usePhoneOtpEnabled();
  const phoneInputRef = useRef<HTMLInputElement>(null);
  const codeInputRef = useRef<HTMLInputElement>(null);
  const pendingFocus = useRef<FocusTarget | null>(null);

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

  // After an error moved the invitee back to step 2, put the cursor on the
  // field to fix — the button they pressed may have just been disabled.
  useEffect(() => {
    const target = pendingFocus.current;
    if (!target) return;
    pendingFocus.current = null;
    (target === "phone" ? phoneInputRef : codeInputRef).current?.focus();
  });

  const effectiveEmail = detail?.invitee_email || emailInput.trim();
  const normalizedEmail = effectiveEmail.toLowerCase();
  const emailLocked = Boolean(detail?.invitee_email);
  const phone = toE164(phoneDigits);
  const pairKey = `${normalizedEmail}|${phone}`;
  const phoneValid = isValidIndianMobile(phoneDigits);
  const cachedToken =
    signupPhone && signupPhone.email === normalizedEmail && signupPhone.phone === phone
      ? signupPhone.token
      : null;
  const willSendCode = phoneOtpEnabled && !cachedToken;
  const inFlight = busy || sendingEmail || resendingPhone;
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

  const rememberCode = (expiresInSeconds?: number) => {
    const key = pairKey;
    const expiresAt =
      Date.now() + (expiresInSeconds ? expiresInSeconds * 1000 : FALLBACK_CODE_LIFETIME_MS);
    setCodesSent((prev) => new Map(prev).set(key, expiresAt));
  };

  const forgetCode = () => {
    const key = pairKey;
    setCodesSent((prev) => {
      if (!prev.has(key)) return prev;
      const next = new Map(prev);
      next.delete(key);
      return next;
    });
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
        pendingFocus.current = "phone";
        return;
      case "rate_limited":
        setError(rateLimitMessage(err));
        return;
      case "invalid_code":
      case "code_expired_or_used":
      case "too_many_attempts":
        if (stage === "verify") {
          // The phone code: an expired or locked one is gone server-side.
          if (errorCode !== "invalid_code") forgetCode();
        } else {
          // The email code on step 2 is wrong or no longer live.
          setStep(2);
          setCode("");
          pendingFocus.current = "code";
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
        pendingFocus.current = "phone";
        return;
      case "policy_acceptance_required":
        setStep(2);
        setError(t("policyRequired"));
        return;
      default:
        // With phone OTP off no code was ever going to be sent.
        setError(
          stage === "request" && phoneOtpEnabled ? tS("errSendFailed") : t("genericError"),
        );
    }
  };

  const sendCode = async () => {
    if (!effectiveEmail) {
      setError(t("emailRequired"));
      return;
    }
    if (inFlight || emailResend.active) return;
    setSendingEmail(true);
    setError(null);
    setEmailTaken(false);
    try {
      await post("/api/v1/auth/otp/request", { email: effectiveEmail });
      setCode("");
      setStep(2);
      emailResend.start();
    } catch (err) {
      if (apiErrorCode(err) === "rate_limited") {
        const wait = seedableWait(err);
        if (wait) emailResend.start(wait);
        setError(rateLimitMessage(err));
      } else {
        setError(t("genericError"));
      }
    } finally {
      setSendingEmail(false);
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
    if (inFlight) return;
    setError(null);
    setPhoneError(null);
    setEmailTaken(false);
    if (!phoneValid) {
      setPhoneError(tS("errInvalidPhone"));
      pendingFocus.current = "phone";
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
      if ((codesSent.get(pairKey) ?? 0) > Date.now()) {
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
      rememberCode(res.expires_in);
      setPhoneCode("");
      setStep(3);
      phoneResend.start();
      setBusy(false);
    } catch (err) {
      if (stage === "request" && codeAlreadySent(err)) {
        // An earlier tap reached the server but its response never reached
        // us: the code is already on its way.
        rememberCode();
        setPhoneCode("");
        setStep(3);
        const wait = seedableWait(err);
        if (wait) phoneResend.start(wait);
      } else {
        handleError(err, stage);
      }
      setBusy(false);
    }
  };

  const verifyPhone = async () => {
    if (inFlight) return;
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
        forgetCode();
      }
      stage = "accept";
      await accept(phoneToken);
    } catch (err) {
      handleError(err, stage);
      setBusy(false);
    }
  };

  const resendPhoneCode = async () => {
    if (inFlight || phoneResend.active) return;
    setError(null);
    setResendingPhone(true);
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
        setBusy(true);
        await accept(res.phone_token);
        return;
      }
      rememberCode(res.expires_in);
      setPhoneCode("");
      phoneResend.start();
    } catch (err) {
      const wait = apiErrorCode(err) === "rate_limited" ? seedableWait(err) : undefined;
      if (wait) phoneResend.start(wait);
      handleError(err, stage);
      setBusy(false);
    } finally {
      setResendingPhone(false);
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
            <button
              className="btn btn-primary"
              type="button"
              onClick={sendCode}
              disabled={inFlight || emailResend.active}
            >
              {sendingEmail
                ? t("sending")
                : emailResend.active
                  ? t("resendEmailIn", { seconds: emailResend.secondsLeft })
                  : t("sendCode")}
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
                ref={codeInputRef}
                className={styles.input}
                value={code}
                onChange={(e) => setCode(asciiDigits(e.target.value).slice(0, 6))}
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="••••••"
                disabled={inFlight}
              />
            </div>
            <div className={styles.linkRow}>
              {emailResend.active ? (
                <span className={styles.muted}>
                  {t("resendEmailIn", { seconds: emailResend.secondsLeft })}
                </span>
              ) : (
                <button
                  type="button"
                  className={styles.linkBtn}
                  onClick={sendCode}
                  disabled={inFlight}
                >
                  {sendingEmail ? t("sending") : t("resendEmailCode")}
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
                disabled={inFlight}
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
                disabled={inFlight}
                invalid={Boolean(shownPhoneError)}
                describedBy="inv-phone-hint"
                className={styles.phoneField}
                inputClassName={styles.phoneFieldInput}
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
                disabled={inFlight}
              />
              <span>{t("agree")}</span>
            </label>
            <button
              className="btn btn-primary"
              type="button"
              onClick={activate}
              disabled={inFlight || !code.trim() || phoneDigits.length !== 10 || !agree}
            >
              {busy
                ? willSendCode
                  ? tL("sending")
                  : t("activating")
                : willSendCode
                  ? tL("continue")
                  : t("activate")}
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
                onChange={(e) => setPhoneCode(asciiDigits(e.target.value).slice(0, 6))}
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
              disabled={inFlight || (phoneCode.length !== 6 && !cachedToken)}
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
                  disabled={inFlight}
                >
                  {resendingPhone ? t("sending") : tS("resendCode")}
                </button>
              )}
              <button
                type="button"
                className={styles.linkBtn}
                onClick={() => {
                  setStep(2);
                  setPhoneCode("");
                  setError(null);
                  pendingFocus.current = "phone";
                }}
                disabled={inFlight}
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
