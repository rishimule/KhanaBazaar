"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import React, { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { ApiError, get, patch, post } from "@/lib/api";
import { formatAddress } from "@/lib/format-address";
import { AddressFields, emptyAddress } from "@/components/AddressFields";
import ServicePicker from "@/components/ServicePicker";
import { Address, SellerProfile, Service, User } from "@/types";
import styles from "./seller-signup.module.css";

/* ------------------------------------------------------------------ */
/* Validation regexes                                                   */
/* ------------------------------------------------------------------ */

const GST_REGEX =
  /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/;
const IFSC_REGEX = /^[A-Z]{4}0[A-Z0-9]{6}$/;
const PHONE_REGEX = /^[6-9]\d{9}$/;

/* ------------------------------------------------------------------ */
/* Step indicator                                                       */
/* ------------------------------------------------------------------ */

const TOTAL_STEPS = 8;

function StepIndicator({ current }: { current: number }) {
  const t = useTranslations("Seller.signup");
  return (
    <>
      <div className={styles.stepIndicator}>
        {Array.from({ length: TOTAL_STEPS }, (_, i) => i + 1).map((n, i) => (
          <React.Fragment key={n}>
            <div
              className={[
                styles.stepDot,
                n < current ? styles.stepDotCompleted : "",
                n === current ? styles.stepDotActive : "",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              {n < current ? "✓" : n}
            </div>
            {i < TOTAL_STEPS - 1 && (
              <div
                className={[
                  styles.stepConnector,
                  n < current ? styles.stepConnectorCompleted : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              />
            )}
          </React.Fragment>
        ))}
      </div>
      <p className={styles.stepLabel}>{t("stepCounter", { current, total: TOTAL_STEPS })}</p>
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Inner component (needs useSearchParams → wrapped in Suspense)       */
/* ------------------------------------------------------------------ */

function SellerSignupPageInner() {
  const t = useTranslations("Seller.signup");
  const tc = useTranslations("Seller.common");
  const router = useRouter();
  const searchParams = useSearchParams();
  const isResubmit = searchParams.get("resubmit") === "true";
  const { token, dbUser, logout } = useAuth();

  /* ---- wizard data state ---- */
  const [currentStep, setCurrentStep] = useState(1);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [emailToken, setEmailToken] = useState("");
  const [phone, setPhone] = useState("");
  const [phoneCode, setPhoneCode] = useState("");
  const [signupToken, setSignupToken] = useState("");
  const [fullName, setFullName] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [serviceIds, setServiceIds] = useState<number[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [address, setAddress] = useState<Address>(emptyAddress());
  const [gstNumber, setGstNumber] = useState("");
  const [fssaiLicense, setFssaiLicense] = useState("");
  const [bankAccountNumber, setBankAccountNumber] = useState("");
  const [bankIfsc, setBankIfsc] = useState("");

  /* ---- UI state ---- */
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<{
    message: string;
    type: "error" | "success";
  } | null>(null);

  /* ---------------------------------------------------------------- */
  /* Helper to clear a single field error without an unused binding   */
  /* ---------------------------------------------------------------- */

  const clearError = (key: string) =>
    setFieldErrors((p) => {
      const next = { ...p };
      delete next[key];
      return next;
    });

  /* ---------------------------------------------------------------- */
  /* Resubmit: jump to step 5 (personal info), pre-fill from profile  */
  /* ---------------------------------------------------------------- */

  useEffect(() => {
    if (!isResubmit) return;
    // Resubmit users already have a verified email + phone on their existing
    // SellerProfile and use a different (authenticated PATCH) path that does
    // not require signup_token. Jump straight to the renamed personal-info
    // step (step 5).
    setCurrentStep(5);
    if (dbUser?.full_name) setFullName(dbUser.full_name);
    if (!token) return;
    get<SellerProfile>("/api/v1/sellers/me/profile", token)
      .then((profile) => {
        // Profile stores E.164 (`+91…`); wizard state is the 10-digit local
        // part since the input has a locked `+91` prefix.
        setPhone((profile.phone ?? "").replace(/^\+91/, ""));
        setBusinessName(profile.business_name);
        setServiceIds(profile.services?.map((s) => s.id) ?? []);
        setAddress(profile.address);
        setGstNumber(profile.gst_number ?? "");
        setFssaiLicense(profile.fssai_license ?? "");
        setBankAccountNumber(profile.bank_account_number ?? "");
        setBankIfsc(profile.bank_ifsc ?? "");
      })
      .catch(() => {
        /* user fills in manually */
      });
  }, [isResubmit, token, dbUser]);

  useEffect(() => {
    get<Service[]>("/api/v1/catalog/services").then(setServices).catch(() => {});
  }, []);

  /* ---------------------------------------------------------------- */
  /* Handlers                                                          */
  /* ---------------------------------------------------------------- */

  const sendOtpRequest = async (): Promise<boolean> => {
    try {
      await post("/api/v1/auth/otp/request", { email });
      return true;
    } catch (err: unknown) {
      const apiErr = err as { detail?: { error?: string; retry_after?: number }; status?: number };
      if (apiErr?.detail?.error === "rate_limited") {
        setToast({
          message: t("errors.rateLimitedSeconds", {
            seconds: apiErr.detail.retry_after ?? 60,
          }),
          type: "error",
        });
      } else {
        setToast({ message: t("errors.sendCodeFailed"), type: "error" });
      }
      return false;
    }
  };

  const handleRequestOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setToast(null);
    if (
      dbUser?.email &&
      email.trim().toLowerCase() === dbUser.email.toLowerCase()
    ) {
      setFieldErrors((p) => ({
        ...p,
        email: t("errors.emailOnCustomerAccount"),
      }));
      return;
    }
    setSubmitting(true);
    const ok = await sendOtpRequest();
    setSubmitting(false);
    if (ok) setCurrentStep(2);
  };

  const handleResendOtp = async () => {
    setToast(null);
    setSubmitting(true);
    const ok = await sendOtpRequest();
    setSubmitting(false);
    if (ok) setToast({ message: t("toast.codeResentInbox"), type: "success" });
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setToast(null);
    try {
      const data = await post<{ email_token: string }>(
        "/api/v1/auth/seller/otp/verify",
        { email, code }
      );
      setEmailToken(data.email_token);
      setCurrentStep(3);
    } catch (err: unknown) {
      const apiErr = err as {
        detail?: { error?: string };
        status?: number;
      };
      const errorCode = apiErr?.detail?.error;
      if (errorCode === "invalid_code") {
        setToast({
          message: t("errors.incorrectCode"),
          type: "error",
        });
      } else if (errorCode === "too_many_attempts") {
        setToast({
          message: t("errors.tooManyAttempts"),
          type: "error",
        });
      } else if (errorCode === "code_expired_or_used") {
        setToast({
          message: t("errors.codeExpired"),
          type: "error",
        });
      } else {
        setToast({
          message: t("errors.verificationFailed"),
          type: "error",
        });
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleSendPhoneCode = async (): Promise<boolean> => {
    setSubmitting(true);
    setToast(null);
    try {
      await post("/api/v1/auth/seller/phone/otp/request", {
        email_token: emailToken,
        phone: `+91${phone}`,
      });
      return true;
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      const code = (apiErr.detail as { error?: string } | string | undefined);
      const errorCode = typeof code === "object" ? code?.error : undefined;
      if (errorCode === "phone_already_registered") {
        setFieldErrors((p) => ({
          ...p,
          phone: t("errors.phoneAlreadyRegistered"),
        }));
      } else if (errorCode === "invalid_phone") {
        setFieldErrors((p) => ({
          ...p,
          phone: t("errors.invalidPhone"),
        }));
      } else if (errorCode === "rate_limited") {
        setToast({
          message: t("errors.rateLimitedWait"),
          type: "error",
        });
      } else {
        setToast({ message: t("errors.sendCodeFailed"), type: "error" });
      }
      return false;
    } finally {
      setSubmitting(false);
    }
  };

  const handlePhoneNext = async () => {
    const errs: Record<string, string> = {};
    if (!phone) errs.phone = t("errors.phoneRequired");
    else if (!PHONE_REGEX.test(phone))
      errs.phone = t("errors.invalidPhone");
    if (Object.keys(errs).length) {
      setFieldErrors((p) => ({ ...p, ...errs }));
      return;
    }
    const ok = await handleSendPhoneCode();
    if (ok) setCurrentStep(4);
  };

  const handleResendPhoneCode = async () => {
    const ok = await handleSendPhoneCode();
    if (ok) setToast({ message: t("toast.codeResentPhone"), type: "success" });
  };

  const handleVerifyPhoneCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setToast(null);
    try {
      const res = await post<{ signup_token: string }>(
        "/api/v1/auth/seller/phone/otp/verify",
        {
          email_token: emailToken,
          phone: `+91${phone}`,
          code: phoneCode,
        }
      );
      setSignupToken(res.signup_token);
      setPhoneCode("");
      setCurrentStep(5);
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      const detail = apiErr.detail as { error?: string } | string | undefined;
      const errorCode = typeof detail === "object" ? detail?.error : undefined;
      if (errorCode === "invalid_code") {
        setToast({ message: t("errors.incorrectCode"), type: "error" });
      } else if (errorCode === "code_expired_or_used") {
        setToast({
          message: t("errors.codeExpired"),
          type: "error",
        });
      } else if (errorCode === "too_many_attempts") {
        setToast({
          message: t("errors.tooManyAttempts"),
          type: "error",
        });
      } else {
        setToast({ message: t("errors.verificationFailed"), type: "error" });
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setToast(null);
    try {
      if (isResubmit) {
        await patch("/api/v1/sellers/me/profile", {
          business_name: businessName,
          service_ids: serviceIds,
          address,
          phone: `+91${phone}`,
          gst_number: gstNumber,
          fssai_license: fssaiLicense,
          bank_account_number: bankAccountNumber,
          bank_ifsc: bankIfsc,
        }, token);
      } else {
        const data = await post<{ access_token: string; user: User }>(
          "/api/v1/auth/seller/register",
          {
            signup_token: signupToken,
            full_name: fullName,
            business_name: businessName,
            service_ids: serviceIds,
            address,
            gst_number: gstNumber,
            fssai_license: fssaiLicense,
            bank_account_number: bankAccountNumber,
            bank_ifsc: bankIfsc,
          }
        );
        localStorage.setItem("kb_token", data.access_token);
      }
      router.push("/seller/signup/pending");
    } catch (err: unknown) {
      const apiErr = err as {
        detail?: { error?: string };
        status?: number;
      };
      const errorCode = apiErr?.detail?.error;
      if (errorCode === "email_already_registered") {
        setToast({
          message: t("errors.emailAlreadyRegistered"),
          type: "error",
        });
      } else if (errorCode === "phone_already_registered") {
        setToast({
          message: t("errors.phoneJustRegistered"),
          type: "error",
        });
        setSignupToken("");
        setPhoneCode("");
        setCurrentStep(3);
      } else if (
        errorCode === "signup_token_expired" ||
        errorCode === "invalid_signup_token"
      ) {
        setToast({
          message: t("errors.phoneVerificationExpired"),
          type: "error",
        });
        setSignupToken("");
        setPhoneCode("");
        setCurrentStep(3);
      } else {
        setToast({
          message: t("errors.somethingWrong"),
          type: "error",
        });
      }
    } finally {
      setSubmitting(false);
    }
  };

  /* ---------------------------------------------------------------- */
  /* Step subtitles                                                    */
  /* ---------------------------------------------------------------- */

  const subtitles: Record<1 | 2 | 3 | 4 | 5 | 6 | 7 | 8, string> = {
    1: t("subtitles.step1"),
    2: t("subtitles.step2", { email }),
    3: t("subtitles.step3"),
    4: t("subtitles.step4", { phone: `+91${phone}` }),
    5: t("subtitles.step5"),
    6: t("subtitles.step6"),
    7: t("subtitles.step7"),
    8: t("subtitles.step8"),
  };

  /* ---------------------------------------------------------------- */
  /* Render                                                            */
  /* ---------------------------------------------------------------- */

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        {/* Header */}
        <div className={styles.cardHeader}>
          <div className={styles.cardLogo}>🏪</div>
          <h1 className={styles.cardTitle}>
            {t.rich("title", {
              accent: (chunks) => (
                <span className={styles.cardTitleAccent}>{chunks}</span>
              ),
            })}
          </h1>
          <p className={styles.cardSubtitle}>
            {subtitles[currentStep as 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8]}
          </p>
        </div>

        {/* Step indicator */}
        <StepIndicator current={currentStep} />

        {/* Banner: customer-account session active — step 1 only (relevant before email is locked in) */}
        {dbUser && !isResubmit && currentStep === 1 && (
          <div className={styles.accountNotice} role="status">
            <span className={styles.accountNoticeText}>
              {t.rich("accountNotice", {
                email: dbUser.email,
                strong: (chunks) => <strong>{chunks}</strong>,
              })}
            </span>
            <button
              type="button"
              className={styles.accountNoticeAction}
              onClick={async () => {
                await logout();
                router.refresh();
              }}
            >
              {t("signOut")}
            </button>
          </div>
        )}

        {/* ---- Step 1: Email ---- */}
        {currentStep === 1 && (
          <form className={styles.form} onSubmit={handleRequestOtp}>
            {toast && (
              <div
                className={
                  toast.type === "success" ? styles.toastSuccess : styles.toast
                }
              >
                {toast.message}
              </div>
            )}
            <div className={styles.inputGroup}>
              <label className={styles.label} htmlFor="email">
                {t("emailLabel")}
              </label>
              <input
                id="email"
                type="email"
                className={
                  fieldErrors.email
                    ? `${styles.input} ${styles.inputError}`
                    : styles.input
                }
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  if (fieldErrors.email) clearError("email");
                }}
                required
                autoComplete="email"
                placeholder="you@example.com"
              />
              {fieldErrors.email && (
                <p className={styles.fieldError}>{fieldErrors.email}</p>
              )}
            </div>
            <button
              type="submit"
              className={styles.submitBtn}
              disabled={submitting}
            >
              {submitting ? t("sendingCode") : t("sendCode")}
            </button>
          </form>
        )}

        {/* ---- Step 2: Verify OTP ---- */}
        {currentStep === 2 && (
          <form className={styles.form} onSubmit={handleVerifyOtp}>
            {toast && (
              <div
                className={
                  toast.type === "success" ? styles.toastSuccess : styles.toast
                }
              >
                {toast.message}
              </div>
            )}
            <div className={styles.inputGroup}>
              <label className={styles.label} htmlFor="otp-code">
                {t("otpLabel")}
              </label>
              <input
                id="otp-code"
                type="text"
                className={styles.otpInput}
                inputMode="numeric"
                pattern="\d{6}"
                maxLength={6}
                value={code}
                onChange={(e) =>
                  setCode(e.target.value.replace(/\D/g, ""))
                }
                required
                autoComplete="one-time-code"
                autoFocus
                placeholder="123456"
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
              <span>{t("didntReceive")}</span>
              <button
                type="button"
                className={styles.resendBtn}
                onClick={handleResendOtp}
                disabled={submitting}
              >
                {t("resendCode")}
              </button>
            </div>
          </form>
        )}

        {/* ---- Step 3: Phone entry ---- */}
        {currentStep === 3 && (
          <>
            {toast && (
              <div
                className={
                  toast.type === "success" ? styles.toastSuccess : styles.toast
                }
              >
                {toast.message}
              </div>
            )}
            <div className={styles.inputGroup}>
              <label className={styles.label} htmlFor="phone">
                {t("mobileLabel")}
              </label>
              <div className={styles.phoneFieldRow}>
                <span className={styles.phonePrefix}>+91</span>
                <input
                  id="phone"
                  type="tel"
                  className={
                    fieldErrors.phone
                      ? `${styles.phoneInput} ${styles.inputError}`
                      : styles.phoneInput
                  }
                  inputMode="numeric"
                  maxLength={10}
                  value={phone}
                  onChange={(e) => {
                    setPhone(e.target.value.replace(/\D/g, "").slice(0, 10));
                    clearError("phone");
                  }}
                  onBlur={() => {
                    if (phone && !PHONE_REGEX.test(phone))
                      setFieldErrors((p) => ({
                        ...p,
                        phone: t("errors.invalidPhone"),
                      }));
                    else clearError("phone");
                  }}
                  placeholder="9876543210"
                  autoComplete="tel-national"
                />
              </div>
              {fieldErrors.phone && (
                <span className={styles.fieldError}>{fieldErrors.phone}</span>
              )}
            </div>
            <div className={styles.btnRow}>
              {!isResubmit && (
                <button
                  type="button"
                  className={styles.backBtn}
                  onClick={() => setCurrentStep(2)}
                >
                  {tc("back")}
                </button>
              )}
              <button
                type="button"
                className={styles.submitBtn}
                onClick={handlePhoneNext}
                disabled={submitting || !PHONE_REGEX.test(phone)}
              >
                {submitting ? t("sendingCode") : t("sendCode")}
              </button>
            </div>
          </>
        )}

        {/* ---- Step 4: Phone OTP verify ---- */}
        {currentStep === 4 && (
          <form className={styles.form} onSubmit={handleVerifyPhoneCode}>
            {toast && (
              <div
                className={
                  toast.type === "success" ? styles.toastSuccess : styles.toast
                }
              >
                {toast.message}
              </div>
            )}
            <div className={styles.inputGroup}>
              <label className={styles.label} htmlFor="phone-code">
                {t("otpLabel")}
              </label>
              <input
                id="phone-code"
                type="text"
                className={styles.otpInput}
                inputMode="numeric"
                pattern="\d{6}"
                maxLength={6}
                value={phoneCode}
                onChange={(e) =>
                  setPhoneCode(e.target.value.replace(/\D/g, "").slice(0, 6))
                }
                required
                autoComplete="one-time-code"
                autoFocus
                placeholder="123456"
              />
            </div>
            <div className={styles.btnRow}>
              <button
                type="button"
                className={styles.backBtn}
                onClick={() => {
                  setPhoneCode("");
                  setCurrentStep(3);
                }}
              >
                {tc("back")}
              </button>
              <button
                type="submit"
                className={styles.submitBtn}
                disabled={submitting || phoneCode.length !== 6}
              >
                {submitting ? t("verifying") : t("verifyCode")}
              </button>
            </div>
            <div className={styles.resendRow}>
              <span>{t("didntReceive")}</span>
              <button
                type="button"
                className={styles.resendBtn}
                onClick={handleResendPhoneCode}
                disabled={submitting}
              >
                {t("resendCode")}
              </button>
            </div>
          </form>
        )}

        {/* ---- Step 5: Personal Info ---- */}
        {currentStep === 5 && (
          <>
            {toast && (
              <div
                className={
                  toast.type === "success" ? styles.toastSuccess : styles.toast
                }
              >
                {toast.message}
              </div>
            )}
            <div className={styles.inputGroup}>
              <label className={styles.label} htmlFor="full-name">
                {t("fullNameLabel")}
              </label>
              <input
                id="full-name"
                type="text"
                className={
                  fieldErrors.fullName
                    ? `${styles.input} ${styles.inputError}`
                    : styles.input
                }
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                onBlur={() => {
                  if (!fullName.trim())
                    setFieldErrors((p) => ({
                      ...p,
                      fullName: t("errors.nameRequired"),
                    }));
                  else clearError("fullName");
                }}
                autoComplete="name"
                placeholder={t("fullNamePlaceholder")}
              />
              {fieldErrors.fullName && (
                <span className={styles.fieldError}>{fieldErrors.fullName}</span>
              )}
            </div>
            <div className={styles.btnRow}>
              {!isResubmit && (
                <button
                  type="button"
                  className={styles.backBtn}
                  onClick={() => setCurrentStep(4)}
                >
                  {tc("back")}
                </button>
              )}
              <button
                type="button"
                className={styles.submitBtn}
                onClick={() => {
                  const errs: Record<string, string> = {};
                  if (!fullName.trim()) errs.fullName = t("errors.nameRequired");
                  if (Object.keys(errs).length) {
                    setFieldErrors((p) => ({ ...p, ...errs }));
                    return;
                  }
                  setCurrentStep(6);
                }}
                disabled={submitting}
              >
                {t("next")}
              </button>
            </div>
          </>
        )}

        {/* ---- Step 6: Business Details ---- */}
        {currentStep === 6 && (
          <>
            {toast && (
              <div
                className={
                  toast.type === "success" ? styles.toastSuccess : styles.toast
                }
              >
                {toast.message}
              </div>
            )}
            <div className={styles.inputGroup}>
              <label className={styles.label} htmlFor="business-name">
                {t("businessNameLabel")}
              </label>
              <input
                id="business-name"
                type="text"
                className={
                  fieldErrors.businessName
                    ? `${styles.input} ${styles.inputError}`
                    : styles.input
                }
                value={businessName}
                onChange={(e) => setBusinessName(e.target.value)}
                onBlur={() => {
                  if (!businessName.trim())
                    setFieldErrors((p) => ({
                      ...p,
                      businessName: t("errors.businessNameRequired"),
                    }));
                  else clearError("businessName");
                }}
                placeholder={t("businessNamePlaceholder")}
              />
              {fieldErrors.businessName && (
                <span className={styles.fieldError}>
                  {fieldErrors.businessName}
                </span>
              )}
            </div>
            <div className={styles.formGroup}>
              <label className={styles.label}>{t("servicesOfferedLabel")}</label>
              <ServicePicker
                selectedIds={serviceIds}
                onChange={(ids) => {
                  setServiceIds(ids);
                  if (ids.length > 0) clearError("services");
                }}
                services={services.length > 0 ? services : undefined}
              />
              {fieldErrors.services && (
                <p className={styles.errorText}>{fieldErrors.services}</p>
              )}
            </div>
            <div className={styles.inputGroup}>
              <label className={styles.label}>{t("businessAddressLabel")}</label>
              <AddressFields
                value={address}
                onChange={setAddress}
                requirePin
                errors={{
                  address_line1: fieldErrors.address_line1,
                  city: fieldErrors.city,
                  state: fieldErrors.state,
                  pincode: fieldErrors.pincode,
                }}
              />
            </div>
            <div className={styles.btnRow}>
              <button
                type="button"
                className={styles.backBtn}
                onClick={() => setCurrentStep(5)}
              >
                {tc("back")}
              </button>
              <button
                type="button"
                className={styles.submitBtn}
                onClick={() => {
                  const errs: Record<string, string> = {};
                  if (!businessName.trim())
                    errs.businessName = t("errors.businessNameRequired");
                  if (serviceIds.length === 0)
                    errs.services = t("errors.selectService");
                  if (!address.address_line1.trim())
                    errs.address_line1 = t("errors.addressLine1Required");
                  if (!address.city.trim()) errs.city = t("errors.cityRequired");
                  if (!address.state) errs.state = t("errors.stateRequired");
                  if (!/^[1-9]\d{5}$/.test(address.pincode))
                    errs.pincode = t("errors.invalidPincode");
                  if (address.latitude == null || address.longitude == null)
                    errs.address_line1 = t("errors.dropPin");
                  if (Object.keys(errs).length) {
                    setFieldErrors((p) => ({ ...p, ...errs }));
                    return;
                  }
                  setCurrentStep(7);
                }}
                disabled={submitting}
              >
                {t("next")}
              </button>
            </div>
          </>
        )}

        {/* ---- Step 7: Compliance & Bank ---- */}
        {currentStep === 7 && (
          <>
            {toast && (
              <div
                className={
                  toast.type === "success" ? styles.toastSuccess : styles.toast
                }
              >
                {toast.message}
              </div>
            )}
            <div className={styles.formGrid}>
              <div className={styles.inputGroup}>
                <label className={styles.label} htmlFor="gst-number">
                  {t("gstLabel")}
                </label>
                <input
                  id="gst-number"
                  type="text"
                  className={
                    fieldErrors.gstNumber
                      ? `${styles.input} ${styles.inputError}`
                      : styles.input
                  }
                  value={gstNumber}
                  onChange={(e) =>
                    setGstNumber(e.target.value.toUpperCase())
                  }
                  onBlur={() => {
                    if (gstNumber && !GST_REGEX.test(gstNumber))
                      setFieldErrors((p) => ({
                        ...p,
                        gstNumber: t("errors.invalidGst"),
                      }));
                    else clearError("gstNumber");
                  }}
                  placeholder="27AAPFU0939F1ZV"
                  maxLength={15}
                />
                {fieldErrors.gstNumber && (
                  <span className={styles.fieldError}>
                    {fieldErrors.gstNumber}
                  </span>
                )}
              </div>
              <div className={styles.inputGroup}>
                <label className={styles.label} htmlFor="fssai-license">
                  {t("fssaiLabel")}
                </label>
                <input
                  id="fssai-license"
                  type="text"
                  className={
                    fieldErrors.fssaiLicense
                      ? `${styles.input} ${styles.inputError}`
                      : styles.input
                  }
                  value={fssaiLicense}
                  onChange={(e) => setFssaiLicense(e.target.value)}
                  onBlur={() => {
                    clearError("fssaiLicense");
                  }}
                  placeholder="12345678901234"
                />
                {fieldErrors.fssaiLicense && (
                  <span className={styles.fieldError}>
                    {fieldErrors.fssaiLicense}
                  </span>
                )}
              </div>
              <div className={styles.inputGroup}>
                <label className={styles.label} htmlFor="bank-account">
                  {t("bankAccountLabel")}
                </label>
                <input
                  id="bank-account"
                  type="text"
                  className={
                    fieldErrors.bankAccountNumber
                      ? `${styles.input} ${styles.inputError}`
                      : styles.input
                  }
                  value={bankAccountNumber}
                  onChange={(e) => setBankAccountNumber(e.target.value)}
                  onBlur={() => {
                    if (bankAccountNumber && !/^\d{9,18}$/.test(bankAccountNumber))
                      setFieldErrors((p) => ({
                        ...p,
                        bankAccountNumber: t("errors.invalidBankAccount"),
                      }));
                    else clearError("bankAccountNumber");
                  }}
                  placeholder="012345678901"
                />
                {fieldErrors.bankAccountNumber && (
                  <span className={styles.fieldError}>
                    {fieldErrors.bankAccountNumber}
                  </span>
                )}
              </div>
              <div className={styles.inputGroup}>
                <label className={styles.label} htmlFor="bank-ifsc">
                  {t("ifscLabel")}
                </label>
                <input
                  id="bank-ifsc"
                  type="text"
                  className={
                    fieldErrors.bankIfsc
                      ? `${styles.input} ${styles.inputError}`
                      : styles.input
                  }
                  value={bankIfsc}
                  onChange={(e) =>
                    setBankIfsc(e.target.value.toUpperCase())
                  }
                  onBlur={() => {
                    if (bankIfsc && !IFSC_REGEX.test(bankIfsc))
                      setFieldErrors((p) => ({
                        ...p,
                        bankIfsc: t("errors.invalidIfsc"),
                      }));
                    else clearError("bankIfsc");
                  }}
                  placeholder="HDFC0001234"
                  maxLength={11}
                />
                {fieldErrors.bankIfsc && (
                  <span className={styles.fieldError}>
                    {fieldErrors.bankIfsc}
                  </span>
                )}
              </div>
            </div>
            <div className={styles.btnRow}>
              <button
                type="button"
                className={styles.backBtn}
                onClick={() => setCurrentStep(6)}
              >
                {tc("back")}
              </button>
              <button
                type="button"
                className={styles.submitBtn}
                onClick={() => {
                  const errs: Record<string, string> = {};
                  if (gstNumber && !GST_REGEX.test(gstNumber))
                    errs.gstNumber = t("errors.invalidGst");
                  if (bankAccountNumber && !/^\d{9,18}$/.test(bankAccountNumber))
                    errs.bankAccountNumber = t("errors.invalidBankAccount");
                  if (bankIfsc && !IFSC_REGEX.test(bankIfsc))
                    errs.bankIfsc = t("errors.invalidIfsc");
                  if (Object.keys(errs).length) {
                    setFieldErrors((p) => ({ ...p, ...errs }));
                    return;
                  }
                  setCurrentStep(8);
                }}
                disabled={submitting}
              >
                {t("next")}
              </button>
            </div>
          </>
        )}

        {/* ---- Step 8: Review & Submit ---- */}
        {currentStep === 8 && (
          <form className={styles.form} onSubmit={handleSubmit}>
            {toast && (
              <div
                className={
                  toast.type === "success" ? styles.toastSuccess : styles.toast
                }
              >
                {toast.message}
              </div>
            )}

            {/* Personal Info section */}
            <div className={styles.reviewSection}>
              <div className={styles.reviewSectionHeader}>
                <span>{t("review.personalInfo")}</span>
                <button
                  type="button"
                  className={styles.editLink}
                  onClick={() => setCurrentStep(5)}
                >
                  {tc("edit")}
                </button>
              </div>
              <div className={styles.reviewRow}>
                <span className={styles.reviewLabel}>{t("fullNameLabel")}</span>
                <span className={styles.reviewValue}>{fullName}</span>
              </div>
              <div className={styles.reviewRow}>
                <span className={styles.reviewLabel}>{t("review.phone")}</span>
                <span className={styles.reviewValue}>+91 {phone}</span>
              </div>
            </div>

            {/* Business Details section */}
            <div className={styles.reviewSection}>
              <div className={styles.reviewSectionHeader}>
                <span>{t("review.businessDetails")}</span>
                <button
                  type="button"
                  className={styles.editLink}
                  onClick={() => setCurrentStep(6)}
                >
                  {tc("edit")}
                </button>
              </div>
              <div className={styles.reviewRow}>
                <span className={styles.reviewLabel}>{t("businessNameLabel")}</span>
                <span className={styles.reviewValue}>{businessName}</span>
              </div>
              <div className={styles.reviewRow}>
                <span className={styles.reviewLabel}>{t("review.services")}</span>
                <span className={styles.reviewValue}>
                  {serviceIds
                    .map((id) => services.find((s) => s.id === id)?.name)
                    .filter(Boolean)
                    .join(", ") || "—"}
                </span>
              </div>
              <div className={styles.reviewRow}>
                <span className={styles.reviewLabel}>{t("review.address")}</span>
                <span className={styles.reviewValue}>{formatAddress(address)}</span>
              </div>
            </div>

            {/* Compliance & Bank section */}
            <div className={styles.reviewSection}>
              <div className={styles.reviewSectionHeader}>
                <span>{t("review.complianceBank")}</span>
                <button
                  type="button"
                  className={styles.editLink}
                  onClick={() => setCurrentStep(7)}
                >
                  {tc("edit")}
                </button>
              </div>
              <div className={styles.reviewRow}>
                <span className={styles.reviewLabel}>{t("review.gstNumber")}</span>
                <span className={styles.reviewValue}>{gstNumber}</span>
              </div>
              <div className={styles.reviewRow}>
                <span className={styles.reviewLabel}>{t("review.fssaiLicense")}</span>
                <span className={styles.reviewValue}>{fssaiLicense}</span>
              </div>
              <div className={styles.reviewRow}>
                <span className={styles.reviewLabel}>{t("review.bankAccount")}</span>
                <span className={styles.reviewValue}>{bankAccountNumber}</span>
              </div>
              <div className={styles.reviewRow}>
                <span className={styles.reviewLabel}>{t("review.ifscCode")}</span>
                <span className={styles.reviewValue}>{bankIfsc}</span>
              </div>
            </div>

            <div className={styles.btnRow}>
              <button
                type="button"
                className={styles.backBtn}
                onClick={() => setCurrentStep(7)}
              >
                {tc("back")}
              </button>
              <button
                type="submit"
                className={styles.submitBtn}
                disabled={submitting}
              >
                {submitting ? t("submitting") : t("submitApplication")}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Default export — wraps inner component in Suspense for useSearchParams */
/* ------------------------------------------------------------------ */

export default function SellerSignupPage() {
  return (
    <Suspense fallback={<div style={{ minHeight: "100vh" }} />}>
      <SellerSignupPageInner />
    </Suspense>
  );
}
