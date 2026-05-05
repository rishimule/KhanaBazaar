"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { get, patch, post } from "@/lib/api";
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

function StepIndicator({ current }: { current: number }) {
  return (
    <>
      <div className={styles.stepIndicator}>
        {[1, 2, 3, 4, 5, 6].map((n, i) => (
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
            {i < 5 && (
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
      <p className={styles.stepLabel}>Step {current} of 6</p>
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Inner component (needs useSearchParams → wrapped in Suspense)       */
/* ------------------------------------------------------------------ */

function SellerSignupPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isResubmit = searchParams.get("resubmit") === "true";
  const { token, dbUser } = useAuth();

  /* ---- wizard data state ---- */
  const [currentStep, setCurrentStep] = useState(1);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [emailToken, setEmailToken] = useState("");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
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
  /* Resubmit: jump to step 3, pre-fill from profile                  */
  /* ---------------------------------------------------------------- */

  useEffect(() => {
    if (!isResubmit) return;
    setCurrentStep(3);
    if (dbUser?.full_name) setFullName(dbUser.full_name);
    if (!token) return;
    get<SellerProfile>("/api/v1/sellers/me/profile", token)
      .then((profile) => {
        setPhone(profile.phone);
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
          message: `Please wait ${apiErr.detail.retry_after ?? 60} seconds before requesting a new code.`,
          type: "error",
        });
      } else {
        setToast({ message: "Failed to send code. Please try again.", type: "error" });
      }
      return false;
    }
  };

  const handleRequestOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setToast(null);
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
    if (ok) setToast({ message: "Code resent! Check your inbox.", type: "success" });
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
          message: "Incorrect code. Please try again.",
          type: "error",
        });
      } else if (errorCode === "too_many_attempts") {
        setToast({
          message: "Too many attempts. Please request a new code.",
          type: "error",
        });
      } else if (errorCode === "code_expired_or_used") {
        setToast({
          message: "Code expired. Please request a new one.",
          type: "error",
        });
      } else {
        setToast({
          message: "Verification failed. Please try again.",
          type: "error",
        });
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
          phone,
          gst_number: gstNumber,
          fssai_license: fssaiLicense,
          bank_account_number: bankAccountNumber,
          bank_ifsc: bankIfsc,
        }, token);
      } else {
        const data = await post<{ access_token: string; user: User }>(
          "/api/v1/auth/seller/register",
          {
            email_token: emailToken,
            full_name: fullName,
            phone,
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
      if (apiErr?.detail?.error === "email_already_registered") {
        setToast({
          message:
            "This email is already registered as a seller. Log in instead.",
          type: "error",
        });
      } else if (apiErr?.status === 400 || apiErr?.status === 410) {
        setToast({
          message: "Verification expired. Please start over.",
          type: "error",
        });
      } else {
        setToast({
          message: "Something went wrong. Please try again.",
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

  const subtitles: Record<1 | 2 | 3 | 4 | 5 | 6, string> = {
    1: "Enter your email to get started",
    2: `Enter the 6-digit code sent to ${email}`,
    3: "Tell us about yourself",
    4: "Tell us about your business",
    5: "Compliance & banking details",
    6: "Review your application",
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
            Sell on{" "}
            <span className={styles.cardTitleAccent}>KhanaBazaar</span>
          </h1>
          <p className={styles.cardSubtitle}>
            {subtitles[currentStep as 1 | 2 | 3 | 4 | 5 | 6]}
          </p>
        </div>

        {/* Step indicator */}
        <StepIndicator current={currentStep} />

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
                Email address
              </label>
              <input
                id="email"
                type="email"
                className={styles.input}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                placeholder="you@example.com"
              />
            </div>
            <button
              type="submit"
              className={styles.submitBtn}
              disabled={submitting}
            >
              {submitting ? "Sending code…" : "Send code"}
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
                One-time code
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
              {submitting ? "Verifying…" : "Verify code"}
            </button>
            <div className={styles.resendRow}>
              <span>Didn&apos;t receive it?</span>
              <button
                type="button"
                className={styles.resendBtn}
                onClick={handleResendOtp}
                disabled={submitting}
              >
                Resend code
              </button>
            </div>
          </form>
        )}

        {/* ---- Step 3: Personal Info ---- */}
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
            <div className={styles.formGrid}>
              <div className={styles.inputGroup}>
                <label className={styles.label} htmlFor="full-name">
                  Full name
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
                        fullName: "Name is required",
                      }));
                    else clearError("fullName");
                  }}
                  autoComplete="name"
                  placeholder="Priya Verma"
                />
                {fieldErrors.fullName && (
                  <span className={styles.fieldError}>
                    {fieldErrors.fullName}
                  </span>
                )}
              </div>
              <div className={styles.inputGroup}>
                <label className={styles.label} htmlFor="phone">
                  Phone number
                </label>
                <input
                  id="phone"
                  type="tel"
                  className={
                    fieldErrors.phone
                      ? `${styles.input} ${styles.inputError}`
                      : styles.input
                  }
                  value={phone}
                  onChange={(e) =>
                    setPhone(
                      e.target.value
                        .replace(/\D/g, "")
                        .slice(0, 10)
                    )
                  }
                  onBlur={() => {
                    if (phone && !PHONE_REGEX.test(phone))
                      setFieldErrors((p) => ({
                        ...p,
                        phone: "Enter a valid 10-digit mobile number",
                      }));
                    else clearError("phone");
                  }}
                  placeholder="9876543210"
                  maxLength={10}
                />
                {fieldErrors.phone && (
                  <span className={styles.fieldError}>
                    {fieldErrors.phone}
                  </span>
                )}
              </div>
            </div>
            <div className={styles.btnRow}>
              {!isResubmit && (
                <button
                  type="button"
                  className={styles.backBtn}
                  onClick={() => setCurrentStep(2)}
                >
                  Back
                </button>
              )}
              <button
                type="button"
                className={styles.submitBtn}
                onClick={() => {
                  const errs: Record<string, string> = {};
                  if (!fullName.trim()) errs.fullName = "Name is required";
                  if (!phone) errs.phone = "Phone is required";
                  else if (!PHONE_REGEX.test(phone))
                    errs.phone = "Enter a valid 10-digit mobile number";
                  if (Object.keys(errs).length) {
                    setFieldErrors((p) => ({ ...p, ...errs }));
                    return;
                  }
                  setCurrentStep(4);
                }}
                disabled={submitting}
              >
                Next
              </button>
            </div>
          </>
        )}

        {/* ---- Step 4: Business Details ---- */}
        {currentStep === 4 && (
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
                Business name
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
                      businessName: "Business name is required",
                    }));
                  else clearError("businessName");
                }}
                placeholder="Sharma Kirana Store"
              />
              {fieldErrors.businessName && (
                <span className={styles.fieldError}>
                  {fieldErrors.businessName}
                </span>
              )}
            </div>
            <div className={styles.formGroup}>
              <label className={styles.label}>Services Offered</label>
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
              <label className={styles.label}>Business address</label>
              <AddressFields
                value={address}
                onChange={setAddress}
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
                onClick={() => setCurrentStep(3)}
              >
                Back
              </button>
              <button
                type="button"
                className={styles.submitBtn}
                onClick={() => {
                  const errs: Record<string, string> = {};
                  if (!businessName.trim())
                    errs.businessName = "Business name is required";
                  if (serviceIds.length === 0)
                    errs.services = "Select at least one service";
                  if (!address.address_line1.trim())
                    errs.address_line1 = "Address line 1 is required";
                  if (!address.city.trim()) errs.city = "City is required";
                  if (!address.state) errs.state = "State is required";
                  if (!/^[1-9]\d{5}$/.test(address.pincode))
                    errs.pincode = "Enter a valid 6-digit pincode";
                  if (Object.keys(errs).length) {
                    setFieldErrors((p) => ({ ...p, ...errs }));
                    return;
                  }
                  setCurrentStep(5);
                }}
                disabled={submitting}
              >
                Next
              </button>
            </div>
          </>
        )}

        {/* ---- Step 5: Compliance & Bank ---- */}
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
            <div className={styles.formGrid}>
              <div className={styles.inputGroup}>
                <label className={styles.label} htmlFor="gst-number">
                  GST number (optional)
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
                        gstNumber:
                          "Enter a valid 15-character GST number (e.g., 27AAPFU0939F1ZV)",
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
                  FSSAI license number (optional)
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
                  Bank account number (optional)
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
                        bankAccountNumber: "Enter a valid bank account number (9–18 digits)",
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
                  Bank IFSC code (optional)
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
                        bankIfsc:
                          "Enter a valid 11-character IFSC code (e.g., HDFC0001234)",
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
                onClick={() => setCurrentStep(4)}
              >
                Back
              </button>
              <button
                type="button"
                className={styles.submitBtn}
                onClick={() => {
                  const errs: Record<string, string> = {};
                  if (gstNumber && !GST_REGEX.test(gstNumber))
                    errs.gstNumber =
                      "Enter a valid 15-character GST number (e.g., 27AAPFU0939F1ZV)";
                  if (bankAccountNumber && !/^\d{9,18}$/.test(bankAccountNumber))
                    errs.bankAccountNumber =
                      "Enter a valid bank account number (9–18 digits)";
                  if (bankIfsc && !IFSC_REGEX.test(bankIfsc))
                    errs.bankIfsc =
                      "Enter a valid 11-character IFSC code (e.g., HDFC0001234)";
                  if (Object.keys(errs).length) {
                    setFieldErrors((p) => ({ ...p, ...errs }));
                    return;
                  }
                  setCurrentStep(6);
                }}
                disabled={submitting}
              >
                Next
              </button>
            </div>
          </>
        )}

        {/* ---- Step 6: Review & Submit ---- */}
        {currentStep === 6 && (
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
                <span>Personal Info</span>
                <button
                  type="button"
                  className={styles.editLink}
                  onClick={() => setCurrentStep(3)}
                >
                  Edit
                </button>
              </div>
              <div className={styles.reviewRow}>
                <span className={styles.reviewLabel}>Full name</span>
                <span className={styles.reviewValue}>{fullName}</span>
              </div>
              <div className={styles.reviewRow}>
                <span className={styles.reviewLabel}>Phone</span>
                <span className={styles.reviewValue}>{phone}</span>
              </div>
            </div>

            {/* Business Details section */}
            <div className={styles.reviewSection}>
              <div className={styles.reviewSectionHeader}>
                <span>Business Details</span>
                <button
                  type="button"
                  className={styles.editLink}
                  onClick={() => setCurrentStep(4)}
                >
                  Edit
                </button>
              </div>
              <div className={styles.reviewRow}>
                <span className={styles.reviewLabel}>Business name</span>
                <span className={styles.reviewValue}>{businessName}</span>
              </div>
              <div className={styles.reviewRow}>
                <span className={styles.reviewLabel}>Services</span>
                <span className={styles.reviewValue}>
                  {serviceIds
                    .map((id) => services.find((s) => s.id === id)?.name)
                    .filter(Boolean)
                    .join(", ") || "—"}
                </span>
              </div>
              <div className={styles.reviewRow}>
                <span className={styles.reviewLabel}>Address</span>
                <span className={styles.reviewValue}>{formatAddress(address)}</span>
              </div>
            </div>

            {/* Compliance & Bank section */}
            <div className={styles.reviewSection}>
              <div className={styles.reviewSectionHeader}>
                <span>Compliance &amp; Bank</span>
                <button
                  type="button"
                  className={styles.editLink}
                  onClick={() => setCurrentStep(5)}
                >
                  Edit
                </button>
              </div>
              <div className={styles.reviewRow}>
                <span className={styles.reviewLabel}>GST number</span>
                <span className={styles.reviewValue}>{gstNumber}</span>
              </div>
              <div className={styles.reviewRow}>
                <span className={styles.reviewLabel}>FSSAI license</span>
                <span className={styles.reviewValue}>{fssaiLicense}</span>
              </div>
              <div className={styles.reviewRow}>
                <span className={styles.reviewLabel}>Bank account</span>
                <span className={styles.reviewValue}>{bankAccountNumber}</span>
              </div>
              <div className={styles.reviewRow}>
                <span className={styles.reviewLabel}>IFSC code</span>
                <span className={styles.reviewValue}>{bankIfsc}</span>
              </div>
            </div>

            <div className={styles.btnRow}>
              <button
                type="button"
                className={styles.backBtn}
                onClick={() => setCurrentStep(5)}
              >
                Back
              </button>
              <button
                type="submit"
                className={styles.submitBtn}
                disabled={submitting}
              >
                {submitting ? "Submitting…" : "Submit application"}
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
