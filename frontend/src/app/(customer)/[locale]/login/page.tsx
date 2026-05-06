"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { apiErrorKey } from "@/lib/errors";
import { User } from "@/types";
import styles from "./page.module.css";

type Step = "email" | "code" | "name";

function getRedirect(user: User): string {
  if (user.role === "admin") return "/admin";
  if (user.role === "seller") return "/seller";
  return "/stores";
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

  useEffect(() => {
    if (!dbUser) return;
    router.push(resolveTarget(dbUser, nextParam));
  }, [dbUser, router, nextParam]);

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
      const result = await verifyOtp(email, code, fullName);
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
            <span className={styles.cardTitleAccent}>KhanaBazaar</span>
          </h1>
          <p className={styles.cardSubtitle}>{subtitle}</p>
        </div>

        {step === "email" && (
          <form className={styles.form} onSubmit={handleRequestOtp}>
            {error && <div className={styles.error}>{error}</div>}
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
            {error && <div className={styles.error}>{error}</div>}
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
            {error && <div className={styles.error}>{error}</div>}
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
            <button
              type="submit"
              className={styles.submitBtn}
              disabled={submitting}
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
