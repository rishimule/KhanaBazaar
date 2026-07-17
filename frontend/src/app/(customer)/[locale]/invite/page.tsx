"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { Suspense, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";

import { ApiError, post } from "@/lib/api";
import { setTokens } from "@/lib/authTokens";
import { acceptCustomerReferral, getInvite, type ReferralInviteDetail } from "@/lib/referrals";
import styles from "./page.module.css";

export default function InviteAcceptPage() {
  return (
    <Suspense fallback={<div className={styles.wrap} />}>
      <InviteAcceptInner />
    </Suspense>
  );
}

function InviteAcceptInner() {
  const t = useTranslations("Invite");
  const params = useParams();
  const searchParams = useSearchParams();
  const locale = (params?.locale as string) || "en";
  const token = searchParams.get("token") || "";

  const [detail, setDetail] = useState<ReferralInviteDetail | null>(null);
  const [invalid, setInvalid] = useState(false);
  const [loading, setLoading] = useState(true);
  const [step, setStep] = useState<1 | 2>(1);
  const [emailInput, setEmailInput] = useState("");
  const [code, setCode] = useState("");
  const [fullName, setFullName] = useState("");
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      })
      .catch(() => setInvalid(true))
      .finally(() => setLoading(false));
  }, [token]);

  const effectiveEmail = detail?.invitee_email || emailInput.trim();
  const emailLocked = Boolean(detail?.invitee_email);

  const sendCode = async () => {
    if (!effectiveEmail) {
      setError(t("emailRequired"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await post("/api/v1/auth/otp/request", { email: effectiveEmail });
      setStep(2);
    } catch {
      setError(t("genericError"));
    } finally {
      setBusy(false);
    }
  };

  const activate = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await acceptCustomerReferral({
        token,
        code: code.trim(),
        email: emailLocked ? undefined : effectiveEmail,
        full_name: fullName.trim() || undefined,
        accept_policies: agree,
      });
      setTokens(res.access_token, res.refresh_token, res.expires_in);
      window.location.assign(`/${locale}/account`);
    } catch (err) {
      if (err instanceof ApiError) {
        const code2 = (err.detail as unknown as { error?: string })?.error;
        if (code2 === "invalid_code") setError(t("invalidCode"));
        else if (code2 === "code_expired_or_used") setError(t("codeExpired"));
        else if (code2 === "policy_acceptance_required") setError(t("policyRequired"));
        else if (code2 === "expired") setError(t("expiredError"));
        else setError(t("genericError"));
      } else {
        setError(t("genericError"));
      }
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

        {step === 1 ? (
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
        ) : (
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
              disabled={busy || !code.trim()}
            >
              {busy ? t("activating") : t("activate")}
            </button>
          </>
        )}
        {error && <div className={styles.errorText} role="alert">{error}</div>}
      </div>
    </div>
  );
}
